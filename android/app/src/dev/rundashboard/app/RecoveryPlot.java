package dev.rundashboard.app;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.view.GestureDetector;
import android.view.MotionEvent;
import android.view.ScaleGestureDetector;
import android.view.View;
import android.view.ViewConfiguration;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Locale;
import org.json.JSONArray;
import org.json.JSONObject;

/** Three independent recovery scales sharing a date axis, as in the web app. */
final class RecoveryPlot extends View {
    interface OnPointClick {void open(JSONObject point);}
    private final JSONArray weeks;
    private final OnPointClick onPointClick;
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private final ChartViewport viewport=new ChartViewport();
    private final String[] keys={"sleep_hours","resting_hr","hrv"};
    private final String[] labels={"Sleep · h","Rest HR · bpm","HRV · ms"};
    private final int[] colors={Color.rgb(63,111,168),Color.rgb(179,78,78),Color.rgb(40,124,113)};
    private final ArrayList<float[]> positions=new ArrayList<>();
    private final ArrayList<JSONObject> measurements=new ArrayList<>();
    private final ScaleGestureDetector scale;
    private final GestureDetector gestures;
    private final float density;
    private final int touchSlop;
    private float left,right,lastX,downX;
    private boolean pinched,dragging;
    RecoveryPlot(Context context,JSONArray weeks,OnPointClick onPointClick){
        super(context);this.weeks=weeks;this.onPointClick=onPointClick;density=getResources().getDisplayMetrics().density;touchSlop=ViewConfiguration.get(context).getScaledTouchSlop();
        long start=LocalDate.parse(weeks.optJSONObject(0).optString("date")).toEpochDay();
        long end=LocalDate.parse(weeks.optJSONObject(weeks.length()-1).optString("date")).toEpochDay();
        viewport.configure(start-.5,end+6.5,0,1,0,1);setFocusable(true);
        setContentDescription("Weekly sleep, resting heart rate, and HRV in three lanes. Pinch to zoom dates, drag when zoomed, double-tap to reset. Tap a measurement for its value and number of measured days.");
        scale=new ScaleGestureDetector(context,new ScaleGestureDetector.SimpleOnScaleGestureListener(){
            public boolean onScaleBegin(ScaleGestureDetector detector){pinched=true;getParent().requestDisallowInterceptTouchEvent(true);return true;}
            public boolean onScale(ScaleGestureDetector detector){if(right<=left)return false;viewport.zoom(detector.getScaleFactor(),(detector.getFocusX()-left)/(right-left),.5);invalidate();return true;}
        });scale.setQuickScaleEnabled(false);
        gestures=new GestureDetector(context,new GestureDetector.SimpleOnGestureListener(){
            public boolean onDown(MotionEvent event){return true;}
            public boolean onDoubleTap(MotionEvent event){pinched=true;resetZoom();return true;}
            public boolean onSingleTapConfirmed(MotionEvent event){if(!pinched&&!dragging)openNearest(event.getX(),event.getY());return true;}
        });
    }
    private float dp(float value){return density*value;}
    String[] visibleDates(){
        long first=Math.max(LocalDate.parse(weeks.optJSONObject(0).optString("date")).toEpochDay(),(long)Math.ceil(viewport.xMin));
        long last=Math.min(LocalDate.now().toEpochDay(),(long)Math.floor(viewport.xMax));
        if(last<first)first=last;
        return new String[]{LocalDate.ofEpochDay(first).toString(),LocalDate.ofEpochDay(last).toString()};
    }
    void resetZoom(){viewport.reset();invalidate();announceForAccessibility("Recovery chart reset");}
    @Override protected void onDraw(Canvas canvas){
        super.onDraw(canvas);positions.clear();measurements.clear();left=dp(42);right=getWidth()-dp(8);
        if(right<=left)return;
        float top=dp(26),bottom=getHeight()-dp(32),slot=(bottom-top)/3;
        paint.setTextSize(dp(10));
        for(int lane=0;lane<keys.length;lane++){
            double min=Double.POSITIVE_INFINITY,max=Double.NEGATIVE_INFINITY;
            for(int i=0;i<weeks.length();i++){
                double value=weeks.optJSONObject(i).optDouble(keys[lane],Double.NaN);
                if(Double.isFinite(value)){min=Math.min(min,value);max=Math.max(max,value);}
            }
            float yTop=top+slot*lane,yBottom=yTop+slot-dp(24);
            paint.setColor(colors[lane]);paint.setTextSize(dp(11));canvas.drawText(labels[lane],left,yTop-dp(8),paint);
            if(!Double.isFinite(min)){paint.setColor(Color.rgb(102,115,109));canvas.drawText("No measurements",left,yTop+dp(25),paint);continue;}
            double padding=lane==0?.35:3;min=Math.max(0,min-padding);max+=padding;
            paint.setTextSize(dp(10));paint.setColor(Color.rgb(223,228,220));canvas.drawLine(left,yTop,right,yTop,paint);canvas.drawLine(left,yBottom,right,yBottom,paint);
            paint.setColor(Color.rgb(102,115,109));
            String high=String.format(Locale.getDefault(),lane==0?"%.1f":"%.0f",max),low=String.format(Locale.getDefault(),lane==0?"%.1f":"%.0f",min);
            canvas.drawText(high,left-dp(6)-paint.measureText(high),yTop+dp(4),paint);canvas.drawText(low,left-dp(6)-paint.measureText(low),yBottom+dp(4),paint);
            canvas.save();canvas.clipRect(left,yTop-dp(4),right,yBottom+dp(4));float[] previous=null;
            for(int i=0;i<weeks.length();i++){
                JSONObject week=weeks.optJSONObject(i);double value=week.optDouble(keys[lane],Double.NaN);if(!Double.isFinite(value))continue;
                long day=LocalDate.parse(week.optString("date")).toEpochDay();
                float x=left+(right-left)*(float)((day-viewport.xMin)/(viewport.xMax-viewport.xMin));float y=yBottom-(yBottom-yTop)*(float)((value-min)/(max-min));
                paint.setColor(colors[lane]);paint.setStrokeWidth(dp(2));if(previous!=null)canvas.drawLine(previous[0],previous[1],x,y,paint);
                canvas.drawCircle(x,y,dp(3.5f),paint);previous=new float[]{x,y};
                if(x>=left&&x<=right){
                    positions.add(new float[]{x,y});
                    try{measurements.add(new JSONObject().put("date",week.optString("date")).put("label",labels[lane]).put("formatted",String.format(Locale.getDefault(),lane==0?"%.2f":"%.1f",value)).put("days",week.optInt(keys[lane]+"_days")));}catch(Exception ignored){}
                }
            }
            canvas.restore();
        }
        paint.setColor(Color.rgb(102,115,109));paint.setTextSize(dp(10));DateTimeFormatter format=DateTimeFormatter.ofPattern("MMM d",Locale.getDefault());
        for(int i=0;i<3;i++){
            String label=LocalDate.ofEpochDay(Math.round(viewport.xMin+(viewport.xMax-viewport.xMin)*i/2)).format(format);
            float x=left+(right-left)*i/2;if(i==1)x-=paint.measureText(label)/2;else if(i==2)x-=paint.measureText(label);canvas.drawText(label,x,bottom+dp(17),paint);
        }
    }
    private void openNearest(float x,float y){
        double nearest=dp(24)*dp(24);int selected=-1;
        for(int i=0;i<positions.size();i++){float[] p=positions.get(i);double d=Math.pow(x-p[0],2)+Math.pow(y-p[1],2);if(d<nearest){nearest=d;selected=i;}}
        performClick();if(selected>=0&&onPointClick!=null)onPointClick.open(measurements.get(selected));
    }
    @Override public boolean onTouchEvent(MotionEvent event){
        if(!isEnabled())return false;int action=event.getActionMasked();
        if(action==MotionEvent.ACTION_DOWN){lastX=downX=event.getX();pinched=dragging=false;if(viewport.changed())getParent().requestDisallowInterceptTouchEvent(true);}
        if(event.getPointerCount()>1){pinched=true;getParent().requestDisallowInterceptTouchEvent(true);}
        scale.onTouchEvent(event);gestures.onTouchEvent(event);
        if(action==MotionEvent.ACTION_MOVE&&!pinched&&event.getPointerCount()==1&&viewport.changed()){
            float x=event.getX();if(Math.abs(x-downX)>touchSlop)dragging=true;if(dragging&&right>left){viewport.pan((x-lastX)/(right-left),0);invalidate();}lastX=x;
        }
        if(action==MotionEvent.ACTION_UP||action==MotionEvent.ACTION_CANCEL)getParent().requestDisallowInterceptTouchEvent(false);
        return true;
    }
    @Override public boolean performClick(){super.performClick();return true;}
}
