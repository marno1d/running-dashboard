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
    private final MaterialPalette palette;
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private final ChartViewport viewport=new ChartViewport();
    private final String[] keys;
    private final String[] labels;
    private final int[] colors;
    private final ArrayList<float[]> positions=new ArrayList<>();
    private final ArrayList<JSONObject> measurements=new ArrayList<>();
    private final ScaleGestureDetector scale;
    private final GestureDetector gestures;
    private final float density;
    private final int touchSlop;
    private float left,right,lastX,downX,downY;
    private JSONObject selected;
    private Runnable viewportListener;
    private boolean pinched,dragging,exploration=true;
    RecoveryPlot(Context context,JSONArray weeks,String metric,OnPointClick onPointClick){
        super(context);palette=MaterialUi.palette(context);this.weeks=weeks;this.onPointClick=onPointClick;density=getResources().getDisplayMetrics().density;touchSlop=ViewConfiguration.get(context).getScaledTouchSlop();
        String[] allKeys={"sleep_hours","resting_hr","hrv"},allLabels={"Sleep · h","Rest HR · bpm","HRV · ms"};
        int[] allColors={palette.chart(Color.rgb(63,111,168)),palette.chart(Color.rgb(179,78,78)),palette.chart(Color.rgb(40,124,113))};
        int index=-1;for(int i=0;i<allKeys.length;i++)if(allKeys[i].equals(metric))index=i;
        keys=index<0?allKeys:new String[]{allKeys[index]};labels=index<0?allLabels:new String[]{allLabels[index]};colors=index<0?allColors:new int[]{allColors[index]};
        long start=LocalDate.parse(weeks.optJSONObject(0).optString("date")).toEpochDay();
        long end=LocalDate.parse(weeks.optJSONObject(weeks.length()-1).optString("date")).toEpochDay();
        viewport.configure(start-.5,end+6.5,0,1,0,1);setFocusable(true);
        setContentDescription("Weekly recovery chart. Tap a measurement for details. Explore the chart for date zoom, panning and an accessible list of values and measured-day counts.");
        scale=new ScaleGestureDetector(context,new ScaleGestureDetector.SimpleOnScaleGestureListener(){
            public boolean onScaleBegin(ScaleGestureDetector detector){pinched=true;getParent().requestDisallowInterceptTouchEvent(true);return true;}
            public boolean onScale(ScaleGestureDetector detector){if(right<=left)return false;viewport.zoom(detector.getScaleFactor(),(detector.getFocusX()-left)/(right-left),.5);invalidate();notifyViewport();return true;}
        });scale.setQuickScaleEnabled(false);
        gestures=new GestureDetector(context,new GestureDetector.SimpleOnGestureListener(){
            public boolean onDown(MotionEvent event){return true;}
            public boolean onDoubleTap(MotionEvent event){pinched=true;resetZoom();return true;}
            public boolean onSingleTapConfirmed(MotionEvent event){if(!pinched&&!dragging)openNearest(event.getX(),event.getY());return true;}
        });
    }
    private float dp(float value){return density*value;}
    private float sp(float value){return android.util.TypedValue.applyDimension(android.util.TypedValue.COMPLEX_UNIT_SP,value,getResources().getDisplayMetrics());}
    void setExplorationEnabled(boolean value){exploration=value;}
    boolean isZoomed(){return viewport.changed();}
    void setViewportListener(Runnable listener){viewportListener=listener;}
    private void notifyViewport(){if(viewportListener!=null)viewportListener.run();}
    void selectPoint(JSONObject point){
        long day=LocalDate.parse(point.optString("date")).toEpochDay();if(day<viewport.xMin||day>viewport.xMax)resetZoom();
        selected=point;invalidate();if(onPointClick!=null)onPointClick.open(point);
    }
    JSONArray dataPoints(){
        JSONArray result=new JSONArray();
        for(int i=0;i<weeks.length();i++)for(int k=0;k<keys.length;k++){
            JSONObject week=weeks.optJSONObject(i);double value=week.optDouble(keys[k],Double.NaN);if(!Double.isFinite(value))continue;
            try{result.put(new JSONObject().put("date",week.optString("date")).put("key",keys[k]).put("label",labels[k]).put("formatted",String.format(Locale.getDefault(),keys[k].equals("sleep_hours")?"%.2f":"%.1f",value)).put("days",week.optInt(keys[k]+"_days")));}catch(Exception ignored){}
        }
        return result;
    }
    String[] visibleDates(){
        long first=Math.max(LocalDate.parse(weeks.optJSONObject(0).optString("date")).toEpochDay(),(long)Math.ceil(viewport.xMin));
        long last=Math.min(LocalDate.now().toEpochDay(),(long)Math.floor(viewport.xMax));
        if(last<first)first=last;
        return new String[]{LocalDate.ofEpochDay(first).toString(),LocalDate.ofEpochDay(last).toString()};
    }
    void resetZoom(){viewport.reset();invalidate();notifyViewport();announceForAccessibility("Recovery chart reset");}
    private String axisValue(int lane,double value){return String.format(Locale.getDefault(),keys[lane].equals("sleep_hours")?"%.1f":"%.0f",value);}
    @Override protected void onDraw(Canvas canvas){
        super.onDraw(canvas);positions.clear();measurements.clear();paint.setTextSize(sp(12));paint.setTypeface(android.graphics.Typeface.create("sans-serif",0));
        double[] minima=new double[keys.length],maxima=new double[keys.length];double[][] ticks=new double[keys.length][];float labelWidth=0;
        for(int lane=0;lane<keys.length;lane++){
            double min=Double.POSITIVE_INFINITY,max=Double.NEGATIVE_INFINITY;
            for(int i=0;i<weeks.length();i++){double value=weeks.optJSONObject(i).optDouble(keys[lane],Double.NaN);if(Double.isFinite(value)){min=Math.min(min,value);max=Math.max(max,value);}}
            double padding=keys[lane].equals("sleep_hours")?.35:3;
            minima[lane]=Math.max(0,min-padding);maxima[lane]=max+padding;ticks[lane]=ChartAxis.ticks(minima[lane],maxima[lane],3,false);
            for(double tick:ticks[lane])labelWidth=Math.max(labelWidth,paint.measureText(axisValue(lane,tick)));
        }
        left=Math.max(dp(30),labelWidth+dp(16));right=getWidth()-dp(8);if(right<=left)return;
        float top=sp(14)+dp(14),bottom=getHeight()-sp(12)-dp(22),slot=(bottom-top)/keys.length;
        for(int lane=0;lane<keys.length;lane++){
            double min=minima[lane],max=maxima[lane];float yTop=top+slot*lane,yBottom=yTop+slot-sp(14)-dp(20);
            paint.setColor(colors[lane]);paint.setTextSize(sp(14));canvas.drawText(labels[lane],left,yTop-dp(9),paint);paint.setTextSize(sp(12));
            if(!Double.isFinite(min)){paint.setColor(palette.muted);canvas.drawText("No measurements",left,yTop+dp(25),paint);continue;}
            for(double tick:ticks[lane]){
                float y=yBottom-(yBottom-yTop)*(float)((tick-min)/(max-min));paint.setColor(palette.outline);paint.setAlpha(110);paint.setStrokeWidth(dp(.75f));canvas.drawLine(left,y,right,y,paint);paint.setAlpha(255);
                String label=axisValue(lane,tick);paint.setColor(palette.muted);canvas.drawText(label,left-dp(10)-paint.measureText(label),y-(paint.ascent()+paint.descent())/2,paint);
            }
            canvas.save();canvas.clipRect(left-dp(8),yTop-dp(8),right+dp(8),yBottom+dp(8));float[] previous=null;
            if(selected!=null&&keys[lane].equals(selected.optString("key"))){
                long day=LocalDate.parse(selected.optString("date")).toEpochDay();float x=left+(right-left)*(float)((day-viewport.xMin)/(viewport.xMax-viewport.xMin));paint.setColor(palette.primary);paint.setAlpha(90);paint.setStrokeWidth(dp(1));canvas.drawLine(x,yTop,x,yBottom,paint);paint.setAlpha(255);
            }
            for(int i=0;i<weeks.length();i++){
                JSONObject week=weeks.optJSONObject(i);double value=week.optDouble(keys[lane],Double.NaN);if(!Double.isFinite(value)){previous=null;continue;}
                long day=LocalDate.parse(week.optString("date")).toEpochDay();float x=left+(right-left)*(float)((day-viewport.xMin)/(viewport.xMax-viewport.xMin));float y=yBottom-(yBottom-yTop)*(float)((value-min)/(max-min));
                paint.setColor(colors[lane]);paint.setStrokeWidth(dp(2));if(previous!=null&&ChartInteraction.adjacentWeeks((long)previous[2],day))canvas.drawLine(previous[0],previous[1],x,y,paint);
                canvas.drawCircle(x,y,dp(3.5f),paint);previous=new float[]{x,y,day};
                if(selected!=null&&keys[lane].equals(selected.optString("key"))&&week.optString("date").equals(selected.optString("date"))){
                    paint.setStyle(Paint.Style.STROKE);paint.setColor(palette.container);paint.setStrokeWidth(dp(3));canvas.drawCircle(x,y,dp(6),paint);paint.setColor(palette.primary);paint.setStrokeWidth(dp(2));canvas.drawCircle(x,y,dp(7),paint);paint.setStyle(Paint.Style.FILL);
                }
                if(x>=left&&x<=right){
                    positions.add(new float[]{x,y});
                    try{measurements.add(new JSONObject().put("date",week.optString("date")).put("key",keys[lane]).put("label",labels[lane]).put("formatted",String.format(Locale.getDefault(),keys[lane].equals("sleep_hours")?"%.2f":"%.1f",value)).put("days",week.optInt(keys[lane]+"_days")));}catch(Exception ignored){}
                }
            }
            canvas.restore();
        }
        paint.setColor(palette.muted);paint.setTextSize(sp(12));DateTimeFormatter format=DateTimeFormatter.ofPattern(viewport.xMax-viewport.xMin>180?"MMM yy":"MMM d",Locale.getDefault());
        long first=(long)Math.ceil(viewport.xMin),last=(long)Math.floor(viewport.xMax);if(last<first)first=last=Math.round((viewport.xMin+viewport.xMax)/2);
        float dateWidth=Math.max(paint.measureText(LocalDate.ofEpochDay(first).format(format)),paint.measureText(LocalDate.ofEpochDay(last).format(format)));
        long[] dateTicks=ChartAxis.dates(viewport.xMin,viewport.xMax,right-left,dateWidth,dp(24));
        for(long day:dateTicks){
            String label=LocalDate.ofEpochDay(day).format(format);
            float x=left+(right-left)*(float)((day-viewport.xMin)/(viewport.xMax-viewport.xMin));x=Math.max(left,Math.min(right-paint.measureText(label),x-paint.measureText(label)/2));canvas.drawText(label,x,bottom+sp(12)+dp(9),paint);
        }
    }
    private void openNearest(float x,float y){
        double nearest=dp(32)*dp(32);int selected=-1;
        for(int i=0;i<positions.size();i++){float[] p=positions.get(i);double d=Math.pow(x-p[0],2)+Math.pow(y-p[1],2);if(d<nearest){nearest=d;selected=i;}}
        performClick();if(selected>=0)selectPoint(measurements.get(selected));
    }
    @Override public boolean onTouchEvent(MotionEvent event){
        if(!isEnabled())return false;int action=event.getActionMasked();
        if(action==MotionEvent.ACTION_DOWN){lastX=downX=event.getX();downY=event.getY();pinched=dragging=false;}
        if(event.getPointerCount()>1){pinched=true;if(!exploration){getParent().requestDisallowInterceptTouchEvent(false);return false;}getParent().requestDisallowInterceptTouchEvent(true);}
        if(exploration)scale.onTouchEvent(event);gestures.onTouchEvent(event);
        if(action==MotionEvent.ACTION_MOVE&&!pinched&&event.getPointerCount()==1){
            float x=event.getX();int direction=ChartInteraction.direction(x-downX,event.getY()-downY,touchSlop);
            if(direction<0&&!dragging){getParent().requestDisallowInterceptTouchEvent(false);return false;}
            if(direction>0&&exploration&&viewport.changed()){
                dragging=true;getParent().requestDisallowInterceptTouchEvent(true);
                if(right>left){viewport.pan((x-lastX)/(right-left),0);invalidate();notifyViewport();}
            }else if(direction!=0)dragging=true;
            lastX=x;
        }
        if(action==MotionEvent.ACTION_UP||action==MotionEvent.ACTION_CANCEL)getParent().requestDisallowInterceptTouchEvent(false);
        return true;
    }
    @Override public boolean performClick(){super.performClick();return true;}
}
