package dev.rundashboard.app;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.DashPathEffect;
import android.graphics.RectF;
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

/** Interactive date/pace chart. Faster paces are higher. */
final class ScatterPlot extends View {
    interface OnPointClick { void open(JSONObject point); }
    private final OnPointClick onPointClick;
    private final JSONArray points;
    private final long start,end;
    private final boolean miles,trial,fixedEasy;
    private final String valueKey, valueLabel;
    private final double reference;
    private final boolean bars;
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private final ArrayList<float[]> positions=new ArrayList<>();
    private final ArrayList<JSONObject> visiblePoints=new ArrayList<>();
    private final float density;
    private final int touchSlop;
    private final ChartViewport viewport=new ChartViewport();
    private final RectF plot=new RectF();
    private final ScaleGestureDetector scale;
    private final GestureDetector gestures;
    private float downX,downY,lastX,lastY;
    private boolean dragging,pinched;
    static final String[] KEYS={"easy","short","medium","long","trial","other","cross_train","cross_interval","strength","warmup","easy_long","rebuild_run","other_run"};
    static final String[] LABELS={"Easy run","Short intervals","Medium intervals","Long intervals","5K time trial","Other / unclassified","Cross-training","Cross-training intervals","Strength","Warmup / cooldown","Easy Long","Rebuild run","Other run"};
    static final int[] COLORS={Color.rgb(76,154,75),Color.rgb(114,92,168),Color.rgb(63,111,168),Color.rgb(40,124,113),Color.rgb(179,78,78),Color.rgb(102,115,109),Color.rgb(201,130,42),Color.rgb(201,130,42),Color.rgb(114,92,168),Color.rgb(102,115,109),Color.rgb(63,111,168),Color.rgb(179,78,78),Color.rgb(102,115,109)};
    ScatterPlot(Context context,JSONArray points,String first,String last,boolean miles,boolean trial,boolean fixedEasy,OnPointClick onPointClick){
        this(context,points,first,last,miles,trial,fixedEasy,null,null,Double.NaN,onPointClick);
    }
    ScatterPlot(Context context,JSONArray points,String first,String last,boolean miles,boolean trial,boolean fixedEasy,String valueKey,String valueLabel,double reference,OnPointClick onPointClick){
        super(context);this.bars=points.length()>0&&points.optJSONObject(0).optBoolean("bar");this.valueKey=valueKey;this.valueLabel=valueLabel;this.reference=reference;this.onPointClick=onPointClick;this.points=points;this.miles=miles;this.trial=trial;this.fixedEasy=fixedEasy;
        start=LocalDate.parse(first).toEpochDay();end=LocalDate.parse(last).toEpochDay();density=getResources().getDisplayMetrics().density;
        touchSlop=ViewConfiguration.get(context).getScaledTouchSlop();setFocusable(true);
        setContentDescription("Date versus "+(valueKey!=null?valueLabel:trial?"fastest 5K time":"pace")+" chart with "+points.length()+" points. Pinch to zoom, drag to pan when zoomed, double-tap or use Reset to reset. Tap a point for run details, also available in Runs.");
        scale=new ScaleGestureDetector(context,new ScaleGestureDetector.SimpleOnScaleGestureListener(){
            @Override public boolean onScaleBegin(ScaleGestureDetector detector){
                pinched=true;getParent().requestDisallowInterceptTouchEvent(true);return viewport.ready();
            }
            @Override public boolean onScale(ScaleGestureDetector detector){
                if(plot.width()<=0||plot.height()<=0)return false;
                viewport.zoom(detector.getScaleFactor(),(detector.getFocusX()-plot.left)/plot.width(),(valueKey!=null?1-(detector.getFocusY()-plot.top)/plot.height():(detector.getFocusY()-plot.top)/plot.height()));invalidate();return true;
            }
        });
        scale.setQuickScaleEnabled(false);
        gestures=new GestureDetector(context,new GestureDetector.SimpleOnGestureListener(){
            @Override public boolean onDown(MotionEvent e){return true;}
            @Override public boolean onDoubleTap(MotionEvent e){pinched=true;resetZoom();return true;}
            @Override public boolean onSingleTapConfirmed(MotionEvent e){if(!pinched&&!dragging)openNearest(e.getX(),e.getY());return true;}
        });
    }
    String[] visibleDates(){
        long first=viewport.ready()?Math.max(start,(long)Math.ceil(viewport.xMin)):start;
        long last=viewport.ready()?Math.min(end,(long)Math.floor(viewport.xMax)):end;
        if(last<first)last=first;
        return new String[]{LocalDate.ofEpochDay(first).toString(),LocalDate.ofEpochDay(last).toString()};
    }
    void resetZoom(){viewport.reset();invalidate();announceForAccessibility("Chart reset");}
    static int index(String category){for(int i=0;i<KEYS.length;i++)if(KEYS[i].equals(category))return i;return 5;}
    static String label(String category){return LABELS[index(category)];}
    static int color(String category){if("prediction".equals(category))return Color.rgb(63,111,168);if("easy_prediction".equals(category))return Color.rgb(76,154,75);return COLORS[index(category)];}
    static String pace(double secondsKm,boolean miles){
        if(!Double.isFinite(secondsKm)||secondsKm<=0)return "No pace";
        long seconds=Math.round(secondsKm*(miles?1.609344:1));return String.format(Locale.getDefault(),"%d:%02d",seconds/60,seconds%60);
    }
    private double value(JSONObject point){if(valueKey!=null)return point.optDouble(valueKey,Double.NaN);return trial?point.optDouble("duration",Double.NaN):point.optDouble("pace",Double.NaN)*(miles?1.609344:1);}
    private String axisValue(double value){return valueKey!=null?String.format(Locale.getDefault(),valueLabel.contains("HOURS")?"%.1f":"%.0f",value):pace(value,false);}
    private float dp(float number){return number*density;}
    @Override protected void onDraw(Canvas canvas){
        super.onDraw(canvas);positions.clear();visiblePoints.clear();
        float left=dp(48),right=getWidth()-dp(12),top=dp(30),bottom=getHeight()-dp(38);plot.set(left,top,right,bottom);
        if(right<=left||bottom<=top)return;
        paint.setTextSize(dp(11));paint.setColor(Color.rgb(97,113,106));
        canvas.drawText(valueKey!=null?valueLabel:trial?"5K TIME · MIN:SEC":miles?"PACE · MIN/MI":"PACE · MIN/KM",left,dp(14),paint);
        double min=Double.POSITIVE_INFINITY,max=0;
        for(int i=0;i<points.length();i++){
            JSONObject point=points.optJSONObject(i);if(point==null)continue;double v=value(point);
            if(Double.isFinite(v)&&(valueKey!=null||v>0)){min=Math.min(min,v);max=Math.max(max,v);}
        }
        boolean empty=!Double.isFinite(min);if(empty){min=trial?1200:240;max=trial?2100:600;}
        if(Double.isFinite(reference)){min=Math.min(min,reference);max=Math.max(max,reference);}
        double step=valueKey!=null?Math.max(1,(max-min)/4):max-min>180?60:30;
        min=Math.max(0,Math.floor((min-(valueKey!=null?step*.3:15))/step)*step);max=Math.ceil((max+(valueKey!=null?step*.3:15))/step)*step;
        if(max-min<(valueKey!=null?1:60)){min=Math.max(0,min-(valueKey!=null?1:30));max+=(valueKey!=null?1:30);}
        if(bars)min=0;
        double initialMin=fixedEasy?420/(miles?1:1.609344):min,initialMax=fixedEasy?600/(miles?1:1.609344):max;
        viewport.configure(start-.5,end+.5,Math.min(min,initialMin),Math.max(max,initialMax),initialMin,initialMax);
        for(int i=0;i<=4;i++){
            float y=top+(bottom-top)*i/4;
            paint.setColor(Color.rgb(232,235,226));paint.setStrokeWidth(dp(1));canvas.drawLine(left,y,right,y,paint);
            String label=axisValue(valueKey!=null?viewport.yMax-(viewport.yMax-viewport.yMin)*i/4:viewport.yMin+(viewport.yMax-viewport.yMin)*i/4);paint.setColor(Color.rgb(97,113,106));
            canvas.drawText(label,left-dp(8)-paint.measureText(label),y+dp(4),paint);
        }
        DateTimeFormatter format=DateTimeFormatter.ofPattern(viewport.xMax-viewport.xMin>180?"MMM yy":"MMM d",Locale.getDefault());
        for(int i=0;i<3;i++){
            long day=Math.round(viewport.xMin+(viewport.xMax-viewport.xMin)*i/2);
            day=Math.max(start,Math.min(end,day));String label=LocalDate.ofEpochDay(day).format(format);
            float x=left+(right-left)*i/2;if(i==1)x-=paint.measureText(label)/2;else if(i==2)x-=paint.measureText(label);
            canvas.drawText(label,x,bottom+dp(23),paint);
        }
        if(empty){paint.setTextSize(dp(13));canvas.drawText("No points",left,(top+bottom)/2,paint);return;}
        if(Double.isFinite(reference)&&reference>=viewport.yMin&&reference<=viewport.yMax){
            float y=top+(bottom-top)*(float)((viewport.yMax-reference)/(viewport.yMax-viewport.yMin));
            paint.setColor(Color.rgb(179,78,78));paint.setStrokeWidth(dp(1));
            canvas.drawLine(left,y,right,y,paint);
        }
        if(bars){
            long injury=LocalDate.of(2025,12,11).toEpochDay(),returned=LocalDate.of(2026,3,30).toEpochDay();
            float x1=left+(right-left)*(float)((injury-viewport.xMin)/(viewport.xMax-viewport.xMin));
            float x2=left+(right-left)*(float)((returned-viewport.xMin)/(viewport.xMax-viewport.xMin));
            if(x2>left&&x1<right){paint.setColor(Color.rgb(247,239,227));canvas.drawRect(Math.max(left,x1),top,Math.min(right,x2),bottom,paint);paint.setColor(Color.rgb(102,115,109));canvas.drawText("injury / rebuild",Math.max(left,x1)+dp(4),top+dp(14),paint);}
        }
        java.util.HashMap<String,float[]> previousPoints=new java.util.HashMap<>();
        canvas.save();canvas.clipRect(new RectF(left-dp(5),top-dp(5),right+dp(5),bottom+dp(5)));
        if(fixedEasy||(!trial&&valueKey==null)){
            JSONObject previous=null;
            paint.setColor(Color.argb(35,76,154,75));
            for(int i=0;i<points.length();i++){
                JSONObject point=points.optJSONObject(i);
                if(point==null||!point.has("range_lower"))continue;
                if(previous!=null){
                    long a=LocalDate.parse(previous.optString("date")).toEpochDay(),b=LocalDate.parse(point.optString("date")).toEpochDay();
                    if(b-a<=45){
                        float xa=left+(right-left)*(float)((a-viewport.xMin)/(viewport.xMax-viewport.xMin));
                        float xb=left+(right-left)*(float)((b-viewport.xMin)/(viewport.xMax-viewport.xMin));
                        double unit=miles?1.609344:1;
                        Path band=new Path();band.moveTo(xa,top+(bottom-top)*(float)((previous.optDouble("range_lower")*unit-viewport.yMin)/(viewport.yMax-viewport.yMin)));
                        band.lineTo(xb,top+(bottom-top)*(float)((point.optDouble("range_lower")*unit-viewport.yMin)/(viewport.yMax-viewport.yMin)));
                        band.lineTo(xb,top+(bottom-top)*(float)((point.optDouble("range_upper")*unit-viewport.yMin)/(viewport.yMax-viewport.yMin)));
                        band.lineTo(xa,top+(bottom-top)*(float)((previous.optDouble("range_upper")*unit-viewport.yMin)/(viewport.yMax-viewport.yMin)));band.close();canvas.drawPath(band,paint);
                    }
                }
                previous=point;
            }
        }
        for(int i=0;i<points.length();i++){
            JSONObject point=points.optJSONObject(i);if(point==null)continue;double v=value(point);
            if(!Double.isFinite(v)||v<viewport.yMin||v>viewport.yMax)continue;
            long day;try{day=LocalDate.parse(point.optString("date")).toEpochDay();}catch(RuntimeException bad){continue;}
            if(day<viewport.xMin||day>viewport.xMax)continue;
            float x=left+(right-left)*(float)((day-viewport.xMin)/(viewport.xMax-viewport.xMin));
            float fraction=(float)((v-viewport.yMin)/(viewport.yMax-viewport.yMin));
            float y=top+(bottom-top)*(valueKey!=null?1-fraction:fraction);
            String series=point.optString("category");
            if(!bars&&((valueKey!=null&&!point.has("id"))||"prediction".equals(series)||"easy_prediction".equals(series)||"short".equals(series)||"medium".equals(series)||"long".equals(series))){
                float[] previousPoint=previousPoints.get(series);
                if(previousPoint!=null&&Math.abs(day-previousPoint[2])<=("easy_prediction".equals(series)?45:30)){
                    paint.setColor(color(series));paint.setStrokeWidth(dp(1.5f));if("prediction".equals(series)||"easy_prediction".equals(series))paint.setPathEffect(new DashPathEffect(new float[]{dp(5),dp(4)},0));canvas.drawLine(previousPoint[0],previousPoint[1],x,y,paint);paint.setPathEffect(null);
                }
                previousPoints.put(series,new float[]{x,y,day});
            }
            paint.setColor("value".equals(valueKey)&&point.has("hr_under_percent")?(point.optDouble("hr_under_percent")>=90?Color.rgb(76,154,75):point.optDouble("hr_under_percent")>=75?Color.rgb(201,130,42):Color.rgb(179,78,78)):color(point.optString("category")));paint.setAlpha(210);
            if(point.has("color"))paint.setColor(point.optInt("color"));
            if(bars){float width=Math.max(dp(2),Math.min(dp(14),(right-left)*5/(float)(viewport.xMax-viewport.xMin)));canvas.drawRoundRect(x-width/2,y,x+width/2,bottom,dp(2),dp(2),paint);}
            else if("trail_running".equals(point.optString("activity_type"))){Path triangle=new Path();triangle.moveTo(x,y-dp(6));triangle.lineTo(x-dp(5),y+dp(4));triangle.lineTo(x+dp(5),y+dp(4));triangle.close();canvas.drawPath(triangle,paint);}
            else canvas.drawCircle(x,y,dp(4),paint);paint.setAlpha(255);
            positions.add(new float[]{x,y});visiblePoints.add(point);
        }
        canvas.restore();
    }
    private void openNearest(float x,float y){
        int nearest=-1;double distance=dp(26)*dp(26);
        for(int i=0;i<positions.size();i++){
            float[] p=positions.get(i);double d=Math.pow(x-p[0],2)+(bars?0:Math.pow(y-p[1],2));if(d<distance){distance=d;nearest=i;}
        }
        performClick();if(nearest>=0&&onPointClick!=null)onPointClick.open(visiblePoints.get(nearest));
    }
    @Override public boolean onTouchEvent(MotionEvent event){
        if(!isEnabled())return false;
        int action=event.getActionMasked();
        if(action==MotionEvent.ACTION_DOWN){downX=lastX=event.getX();downY=lastY=event.getY();dragging=false;pinched=false;
            if(viewport.changed())getParent().requestDisallowInterceptTouchEvent(true);
        }
        if(event.getPointerCount()>1){pinched=true;getParent().requestDisallowInterceptTouchEvent(true);}
        scale.onTouchEvent(event);gestures.onTouchEvent(event);
        if(action==MotionEvent.ACTION_MOVE&&!pinched&&event.getPointerCount()==1&&viewport.changed()){
            float x=event.getX(),y=event.getY();
            if(!dragging&&Math.hypot(x-downX,y-downY)>touchSlop){dragging=true;getParent().requestDisallowInterceptTouchEvent(true);}
            if(dragging&&plot.width()>0&&plot.height()>0){viewport.pan((x-lastX)/plot.width(),(valueKey!=null?-1:1)*(y-lastY)/plot.height());invalidate();}
            lastX=x;lastY=y;
        }
        if(action==MotionEvent.ACTION_UP||action==MotionEvent.ACTION_CANCEL)getParent().requestDisallowInterceptTouchEvent(false);
        return true;
    }
    @Override public boolean performClick(){super.performClick();return true;}
}
