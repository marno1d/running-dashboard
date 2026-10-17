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
    private final MaterialPalette palette;
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
    private boolean dragging,pinched,exploration=true;
    private JSONObject selected;
    private Runnable viewportListener;
    static final String[] KEYS={"easy","short","medium","long","trial","other","cross_train","cross_interval","strength","warmup","easy_long","rebuild_run","other_run"};
    static final String[] LABELS={"Easy run","Short intervals","Medium intervals","Long intervals","5K time trial","Other / unclassified","Cross-training","Cross-training intervals","Strength","Warmup / cooldown","Easy Long","Rebuild run","Other run"};
    static final int[] COLORS=MaterialPalette.SERIES;
    ScatterPlot(Context context,JSONArray points,String first,String last,boolean miles,boolean trial,boolean fixedEasy,OnPointClick onPointClick){
        this(context,points,first,last,miles,trial,fixedEasy,null,null,Double.NaN,onPointClick);
    }
    ScatterPlot(Context context,JSONArray points,String first,String last,boolean miles,boolean trial,boolean fixedEasy,String valueKey,String valueLabel,double reference,OnPointClick onPointClick){
        super(context);palette=MaterialUi.palette(context);this.bars=points.length()>0&&points.optJSONObject(0).optBoolean("bar");this.valueKey=valueKey;this.valueLabel=valueLabel;this.reference=reference;this.onPointClick=onPointClick;this.points=points;this.miles=miles;this.trial=trial;this.fixedEasy=fixedEasy;
        start=LocalDate.parse(first).toEpochDay();end=LocalDate.parse(last).toEpochDay();density=getResources().getDisplayMetrics().density;
        touchSlop=ViewConfiguration.get(context).getScaledTouchSlop();setFocusable(true);
        setContentDescription("Date versus "+(valueKey!=null?valueLabel:trial?"fastest 5K time":"pace")+" chart with "+points.length()+" points. Tap a point for details. Explore the chart for zoom, date panning and an accessible data list.");
        scale=new ScaleGestureDetector(context,new ScaleGestureDetector.SimpleOnScaleGestureListener(){
            @Override public boolean onScaleBegin(ScaleGestureDetector detector){
                pinched=true;getParent().requestDisallowInterceptTouchEvent(true);return viewport.ready();
            }
            @Override public boolean onScale(ScaleGestureDetector detector){
                if(plot.width()<=0||plot.height()<=0)return false;
                viewport.zoom(detector.getScaleFactor(),(detector.getFocusX()-plot.left)/plot.width(),(valueKey!=null?1-(detector.getFocusY()-plot.top)/plot.height():(detector.getFocusY()-plot.top)/plot.height()));invalidate();notifyViewport();return true;
            }
        });
        scale.setQuickScaleEnabled(false);
        gestures=new GestureDetector(context,new GestureDetector.SimpleOnGestureListener(){
            @Override public boolean onDown(MotionEvent e){return true;}
            @Override public boolean onDoubleTap(MotionEvent e){pinched=true;resetZoom();return true;}
            @Override public boolean onSingleTapConfirmed(MotionEvent e){if(!pinched&&!dragging)openNearest(e.getX(),e.getY());return true;}
        });
    }
    void setExplorationEnabled(boolean value){exploration=value;}
    String[] visibleDates(){
        long first=viewport.ready()?Math.max(start,(long)Math.ceil(viewport.xMin)):start;
        long last=viewport.ready()?Math.min(end,(long)Math.floor(viewport.xMax)):end;
        if(last<first)first=last=Math.max(start,Math.min(end,Math.round((viewport.xMin+viewport.xMax)/2)));
        return new String[]{LocalDate.ofEpochDay(first).toString(),LocalDate.ofEpochDay(last).toString()};
    }
    void resetZoom(){viewport.reset();invalidate();notifyViewport();announceForAccessibility("Chart reset");}
    boolean isZoomed(){return viewport.changed();}
    void setViewportListener(Runnable listener){viewportListener=listener;}
    private void notifyViewport(){if(viewportListener!=null)viewportListener.run();}
    void selectPoint(JSONObject point){
        if(viewport.ready()){
            long day=LocalDate.parse(point.optString("date")).toEpochDay();double v=value(point);
            if(day<viewport.xMin||day>viewport.xMax||v<viewport.yMin||v>viewport.yMax)resetZoom();
        }
        selected=point;invalidate();if(onPointClick!=null)onPointClick.open(point);
    }
    static int index(String category){for(int i=0;i<KEYS.length;i++)if(KEYS[i].equals(category))return i;return 5;}
    static String label(String category){return LABELS[index(category)];}
    static int color(String category){if("prediction".equals(category))return Color.rgb(63,111,168);if("easy_prediction".equals(category))return Color.rgb(57,124,58);return COLORS[index(category)];}
    static String pace(double secondsKm,boolean miles){
        if(!Double.isFinite(secondsKm)||secondsKm<=0)return "No pace";
        long seconds=Math.round(secondsKm*(miles?1.609344:1));return String.format(Locale.getDefault(),"%d:%02d",seconds/60,seconds%60);
    }
    private double value(JSONObject point){if(valueKey!=null)return point.optDouble(valueKey,Double.NaN);return trial?point.optDouble("duration",Double.NaN):point.optDouble("pace",Double.NaN)*(miles?1.609344:1);}
    private String axisValue(double value){return valueKey!=null?new java.text.DecimalFormat("0.##").format(value):pace(value,false);}
    private float dp(float number){return number*density;}
    private float sp(float value){return android.util.TypedValue.applyDimension(android.util.TypedValue.COMPLEX_UNIT_SP,value,getResources().getDisplayMetrics());}
    private String axisTitle(){
        if(valueKey==null)return trial?"min:sec":miles?"min/mi":"min/km";
        if("hr_under_percent".equals(valueKey)||valueLabel.contains("%"))return "%";
        if(valueLabel.contains("BPM"))return "bpm";
        if(valueLabel.contains("HOUR"))return "hours";
        return valueLabel.contains("DISTANCE")?(miles?"mi":"km"):"load";
    }
    @Override protected void onDraw(Canvas canvas){
        super.onDraw(canvas);positions.clear();visiblePoints.clear();
        paint.setTextSize(sp(12));paint.setTypeface(android.graphics.Typeface.create("sans-serif",0));
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
        if("hr_under_percent".equals(valueKey)||(valueLabel!=null&&valueLabel.contains("%"))){min=0;max=100;}
        double initialMin=fixedEasy?420/(miles?1:1.609344):min,initialMax=fixedEasy?600/(miles?1:1.609344):max;
        viewport.configure(start-.5,end+.5,Math.min(min,initialMin),Math.max(max,initialMax),initialMin,initialMax);
        double minimumStep=valueKey!=null&&!valueLabel.contains("HOUR")&&!valueLabel.contains("DISTANCE")?1:0;
        double[] ticks=ChartAxis.ticks(viewport.yMin,viewport.yMax,4,valueKey==null,minimumStep);
        float labelWidth=0;for(double tick:ticks)labelWidth=Math.max(labelWidth,paint.measureText(axisValue(tick)));
        float left=dp(6)+labelWidth+dp(10),right=getWidth()-dp(8),top=sp(12)+dp(14),bottom=getHeight()-sp(12)-dp(20);plot.set(left,top,right,bottom);
        if(right<=left||bottom<=top)return;
        paint.setColor(palette.muted);canvas.drawText(axisTitle(),left,sp(12),paint);
        String direction="Faster ↑";
        if(valueKey==null&&paint.measureText(axisTitle())+paint.measureText(direction)+dp(20)<right-left)canvas.drawText(direction,right-paint.measureText(direction),sp(12),paint);
        for(double tick:ticks){
            float fraction=(float)((tick-viewport.yMin)/(viewport.yMax-viewport.yMin));
            float y=top+(bottom-top)*(valueKey!=null?1-fraction:fraction);
            paint.setColor(palette.outline);paint.setAlpha(110);paint.setStrokeWidth(dp(.75f));canvas.drawLine(left,y,right,y,paint);paint.setAlpha(255);
            String label=axisValue(tick);paint.setColor(palette.muted);canvas.drawText(label,left-dp(10)-paint.measureText(label),y-(paint.ascent()+paint.descent())/2,paint);
        }
        DateTimeFormatter format=DateTimeFormatter.ofPattern(viewport.xMax-viewport.xMin>180?"MMM yy":"MMM d",Locale.getDefault());
        long first=Math.max(start,(long)Math.ceil(viewport.xMin)),last=Math.min(end,(long)Math.floor(viewport.xMax));if(last<first)first=last=Math.max(start,Math.min(end,Math.round((viewport.xMin+viewport.xMax)/2)));
        float dateWidth=Math.max(paint.measureText(LocalDate.ofEpochDay(first).format(format)),paint.measureText(LocalDate.ofEpochDay(last).format(format)));
        long[] dateTicks=ChartAxis.dates(viewport.xMin,viewport.xMax,right-left,dateWidth,dp(24));
        for(long day:dateTicks){
            String label=LocalDate.ofEpochDay(day).format(format);
            float x=left+(right-left)*(float)((day-viewport.xMin)/(viewport.xMax-viewport.xMin));
            x=Math.max(left,Math.min(right-paint.measureText(label),x-paint.measureText(label)/2));
            paint.setColor(palette.muted);canvas.drawText(label,x,bottom+sp(12)+dp(9),paint);
        }
        if(empty){paint.setTextSize(sp(14));canvas.drawText("No points",left,(top+bottom)/2,paint);return;}
        if(Double.isFinite(reference)&&reference>=viewport.yMin&&reference<=viewport.yMax){
            float y=top+(bottom-top)*(float)((viewport.yMax-reference)/(viewport.yMax-viewport.yMin));
            paint.setColor(palette.chart(Color.rgb(179,78,78)));paint.setStrokeWidth(dp(1));
            canvas.drawLine(left,y,right,y,paint);
        }
        if(bars){
            long injury=LocalDate.of(2025,12,11).toEpochDay(),returned=LocalDate.of(2026,3,30).toEpochDay();
            float x1=left+(right-left)*(float)((injury-viewport.xMin)/(viewport.xMax-viewport.xMin));
            float x2=left+(right-left)*(float)((returned-viewport.xMin)/(viewport.xMax-viewport.xMin));
            if(x2>left&&x1<right){paint.setColor(palette.dark?0x2696621b:0x1896621b);canvas.drawRect(Math.max(left,x1),top,Math.min(right,x2),bottom,paint);}
        }
        java.util.HashMap<String,float[]> previousPoints=new java.util.HashMap<>();
        canvas.save();canvas.clipRect(new RectF(left-dp(8),top-dp(8),right+dp(8),bottom+dp(8)));
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
        if(selected!=null){
            long day=LocalDate.parse(selected.optString("date")).toEpochDay();
            if(day>=viewport.xMin&&day<=viewport.xMax){float x=left+(right-left)*(float)((day-viewport.xMin)/(viewport.xMax-viewport.xMin));paint.setColor(palette.primary);paint.setAlpha(100);paint.setStrokeWidth(dp(1));paint.setPathEffect(new DashPathEffect(new float[]{dp(3),dp(4)},0));canvas.drawLine(x,top,x,bottom,paint);paint.setPathEffect(null);paint.setAlpha(255);}
        }
        java.util.HashMap<String,Float> markerX=new java.util.HashMap<>();
        for(int i=0;i<points.length();i++){
            JSONObject point=points.optJSONObject(i);if(point==null)continue;double v=value(point);
            if(!Double.isFinite(v)||v<viewport.yMin||v>viewport.yMax)continue;
            long day;try{day=LocalDate.parse(point.optString("date")).toEpochDay();}catch(RuntimeException bad){continue;}
            if(day<viewport.xMin||day>viewport.xMax)continue;
            float x=left+(right-left)*(float)((day-viewport.xMin)/(viewport.xMax-viewport.xMin));
            float fraction=(float)((v-viewport.yMin)/(viewport.yMax-viewport.yMin));
            float y=top+(bottom-top)*(valueKey!=null?1-fraction:fraction);
            String series=point.optString("category");
            if(!bars&&((valueKey!=null&&!point.has("id"))||"prediction".equals(series)||"easy_prediction".equals(series))){
                float[] previousPoint=previousPoints.get(series);
                if(previousPoint!=null&&Math.abs(day-previousPoint[2])<=("easy_prediction".equals(series)?45:30)){
                    paint.setColor(palette.chart(color(series)));paint.setStrokeWidth(dp(2));if("prediction".equals(series)||"easy_prediction".equals(series))paint.setPathEffect(new DashPathEffect(new float[]{dp(5),dp(4)},0));canvas.drawLine(previousPoint[0],previousPoint[1],x,y,paint);paint.setPathEffect(null);
                }
                previousPoints.put(series,new float[]{x,y,day});
            }
            paint.setColor(palette.chart(("value".equals(valueKey)||"average_hr".equals(valueKey)||"hr_under_percent".equals(valueKey))&&point.has("hr_under_percent")?(point.optDouble("hr_under_percent")>=90?Color.rgb(57,124,58):point.optDouble("hr_under_percent")>=75?Color.rgb(150,98,27):Color.rgb(179,78,78)):color(point.optString("category"))));paint.setAlpha(210);
            if(point.has("color"))paint.setColor(point.optInt("color"));
            if(bars){float width=Math.max(dp(3),Math.min(dp(28),(right-left)*5.2f/(float)(viewport.xMax-viewport.xMin)));canvas.drawRoundRect(x-width/2,y,x+width/2,bottom,dp(3),dp(3),paint);}
            else if(("prediction".equals(series)||"easy_prediction".equals(series))&&point!=selected&&markerX.containsKey(series)&&Math.abs(x-markerX.get(series))<dp(14)){}
            else if("trial".equals(series)){paint.setColor(palette.container);canvas.drawCircle(x,y,dp(5.5f),paint);paint.setColor(palette.chart(color(series)));paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(dp(2));canvas.drawCircle(x,y,dp(5),paint);paint.setStyle(Paint.Style.FILL);}
            else if("trail_running".equals(point.optString("activity_type"))){Path triangle=new Path();triangle.moveTo(x,y-dp(6));triangle.lineTo(x-dp(5),y+dp(4));triangle.lineTo(x+dp(5),y+dp(4));triangle.close();canvas.drawPath(triangle,paint);}
            else if("prediction".equals(series)||"short".equals(series)){
                Path diamond=new Path();diamond.moveTo(x,y-dp(5));diamond.lineTo(x+dp(5),y);diamond.lineTo(x,y+dp(5));diamond.lineTo(x-dp(5),y);diamond.close();canvas.drawPath(diamond,paint);
            }else if("easy_prediction".equals(series)||"medium".equals(series))canvas.drawRect(x-dp(4),y-dp(4),x+dp(4),y+dp(4),paint);
            else canvas.drawCircle(x,y,dp(points.length()>100?3:4),paint);paint.setAlpha(255);
            if(!markerX.containsKey(series)||Math.abs(x-markerX.get(series))>=dp(14))markerX.put(series,x);
            if(point==selected){
                paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(dp(3));paint.setColor(palette.container);canvas.drawCircle(x,y,dp(6),paint);
                paint.setStrokeWidth(dp(2));paint.setColor(palette.primary);canvas.drawCircle(x,y,dp(7),paint);paint.setStyle(Paint.Style.FILL);
            }
            positions.add(new float[]{x,y});visiblePoints.add(point);
        }
        canvas.restore();
    }
    private void openNearest(float x,float y){
        int nearest=-1;double distance=dp(32)*dp(32);
        for(int i=0;i<positions.size();i++){
            float[] p=positions.get(i);double d=Math.pow(x-p[0],2)+(bars?0:Math.pow(y-p[1],2));if(d<distance){distance=d;nearest=i;}
        }
        performClick();if(nearest>=0)selectPoint(visiblePoints.get(nearest));
    }
    @Override public boolean onTouchEvent(MotionEvent event){
        if(!isEnabled())return false;
        int action=event.getActionMasked();
        if(action==MotionEvent.ACTION_DOWN){downX=lastX=event.getX();downY=lastY=event.getY();dragging=false;pinched=false;}
        if(event.getPointerCount()>1){pinched=true;if(!exploration){getParent().requestDisallowInterceptTouchEvent(false);return false;}getParent().requestDisallowInterceptTouchEvent(true);}
        if(exploration)scale.onTouchEvent(event);gestures.onTouchEvent(event);
        if(action==MotionEvent.ACTION_MOVE&&!pinched&&event.getPointerCount()==1){
            float x=event.getX(),y=event.getY();int direction=ChartInteraction.direction(x-downX,y-downY,touchSlop);
            if(direction<0&&!dragging){getParent().requestDisallowInterceptTouchEvent(false);return false;}
            if(direction>0&&exploration&&viewport.changed()){
                dragging=true;getParent().requestDisallowInterceptTouchEvent(true);
                if(plot.width()>0){viewport.pan((x-lastX)/plot.width(),0);invalidate();notifyViewport();}
            }else if(direction!=0)dragging=true;
            lastX=x;lastY=y;
        }
        if(action==MotionEvent.ACTION_UP||action==MotionEvent.ACTION_CANCEL)getParent().requestDisallowInterceptTouchEvent(false);
        return true;
    }
    @Override public boolean performClick(){super.performClick();return true;}
}
