package dev.rundashboard.app;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.view.MotionEvent;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;
import java.util.Locale;
import java.util.function.IntConsumer;
import org.json.JSONArray;
import org.json.JSONObject;

/** A lightweight route drawing and elevation chart driven by one distance cursor. */
final class WorkoutExplorer extends LinearLayout {
    private final MaterialPalette palette;
    private final boolean miles;
    private final WorkoutTrace trace;
    private final TextView stepText,valueText;
    private final Drawing map,chart;
    private final SeekBar slider;
    private IntConsumer listener;
    private double selected;
    WorkoutExplorer(Context context,MaterialPalette palette,boolean miles,JSONObject data,JSONObject plan){
        super(context);this.palette=palette;this.miles=miles;setOrientation(VERTICAL);
        JSONArray rows=plan.optJSONArray("splits");boolean easy=rows!=null&&rows.length()>0;if(!easy)rows=plan.optJSONArray("phases");
        int count=rows.length(),reps=0;JSONArray phases=plan.optJSONArray("phases");
        for(int i=0;i<phases.length();i++)reps=Math.max(reps,phases.optJSONObject(i).optInt("rep"));
        double[] starts=new double[count],ends=new double[count];String[] labels=new String[count];
        for(int i=0;i<count;i++){
            JSONObject row=rows.optJSONObject(i);starts[i]=row.optDouble("start");ends[i]=row.optDouble("end");String kind=row.optString("kind");
            labels[i]=easy?"Mile "+row.optInt("index")+(row.optBoolean("partial")?" · final partial mile":""):
                kind.equals("walk")?"Walking recovery · after rep "+row.optInt("rep"):
                kind.equals("work")?"Rep "+row.optInt("rep")+" of "+reps:
                kind.equals("warmup")?"Warm-up · 128 bpm":kind.equals("cooldown")?"Cooldown · 128 bpm":"Easy · 128 bpm";
        }
        trace=new WorkoutTrace(numbers(data.optJSONArray("nodes")),numbers(data.optJSONArray("paces")),starts,ends,labels);
        stepText=label(15,palette.primary,true);stepText.setMinHeight(dp(24));addView(stepText,new LayoutParams(-1,-2));
        valueText=label(14,palette.ink,false);valueText.setMinHeight(dp(60));valueText.setMaxLines(4);addView(valueText,new LayoutParams(-1,-2));
        map=new Drawing(context,false);addView(map,new LayoutParams(-1,dp(132)));
        chart=new Drawing(context,true);addView(chart,new LayoutParams(-1,dp(112)));
        slider=new SeekBar(context);slider.setMax(10000);slider.setProgressTintList(android.content.res.ColorStateList.valueOf(palette.primary));
        slider.setThumbTintList(android.content.res.ColorStateList.valueOf(palette.primary));slider.setContentDescription("Position along the planned workout");
        addView(slider,new LayoutParams(-1,dp(48)));
        slider.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){
            public void onProgressChanged(SeekBar bar,int progress,boolean user){if(user)select(trace.distance*progress/10000.);}
            public void onStartTrackingTouch(SeekBar bar){bar.getParent().requestDisallowInterceptTouchEvent(true);}
            public void onStopTrackingTouch(SeekBar bar){bar.getParent().requestDisallowInterceptTouchEvent(false);}
        });
        TextView hint=label(12,palette.muted,false);hint.setText("Drag the elevation chart or slider · Tap a step below\nPredicted pace uses the terrain over each 100 m section.");addView(hint,new LayoutParams(-1,-2));
        select(0);
    }
    private double[][] numbers(JSONArray rows){
        double[][] values=new double[rows.length()][];
        for(int i=0;i<rows.length();i++){JSONArray row=rows.optJSONArray(i);values[i]=new double[row.length()];for(int j=0;j<row.length();j++)values[i][j]=row.isNull(j)?Double.NaN:row.optDouble(j);}
        return values;
    }
    private int dp(float value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private TextView label(int size,int color,boolean bold){TextView view=new TextView(getContext());view.setTextSize(size);view.setTextColor(color);if(bold)view.setTypeface(null,android.graphics.Typeface.BOLD);return view;}
    void setStepListener(IntConsumer listener){this.listener=listener;select(selected);}
    void selectStep(int index){select(trace.starts[index]);}
    private void select(double at){
        selected=trace.clamp(at);int step=trace.step(selected);double[] point=trace.point(selected);
        stepText.setText(trace.labels[step]);double seconds=trace.pace(selected)*(miles?1.609344:1);int rounded=(int)Math.round(seconds);
        String pace=String.format(Locale.getDefault(),"%d:%02d",rounded/60,rounded%60);
        boolean walking=trace.labels[step].startsWith("Walking");
        valueText.setText(String.format(Locale.getDefault(),"%s %s /%s\n%.2f %s · elevation %.0f ft%s",walking?"Walking pace":"Predicted pace here",pace,miles?"mi":"km",selected/(miles?1609.344:1000),miles?"mi":"km",point[3],Double.isFinite(point[1])?"":"\nEstimated terrain · GPS unavailable"));
        slider.setProgress((int)Math.round(selected/trace.distance*10000));map.invalidate();chart.invalidate();
        if(listener!=null)listener.accept(step);
    }
    private final class Drawing extends View {
        private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        private final boolean elevation;
        private float left,right,top,bottom,offsetX,offsetY,scale;
        private double minHeight,maxHeight;
        Drawing(Context context,boolean elevation){super(context);this.elevation=elevation;setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);}
        private float x(double[] point){return elevation?left+(float)(point[0]/trace.distance)*(right-left):offsetX+(float)point[1]*scale;}
        private float y(double[] point){return elevation?bottom-(float)((point[3]-minHeight)/(maxHeight-minHeight))*(bottom-top):offsetY+(float)point[2]*scale;}
        private void line(Canvas canvas,double from,double to,int color,float width){
            Path path=new Path();boolean started=false;double[] first=trace.point(from);
            if(Double.isFinite(elevation?first[3]:first[1])){path.moveTo(x(first),y(first));started=true;}
            for(double[] point:trace.nodes){
                if(point[0]<=from||point[0]>=to)continue;
                if(!Double.isFinite(elevation?point[3]:point[1])){started=false;continue;}
                if(started)path.lineTo(x(point),y(point));else{path.moveTo(x(point),y(point));started=true;}
            }
            double[] last=trace.point(to);
            if(started&&Double.isFinite(elevation?last[3]:last[1]))path.lineTo(x(last),y(last));
            paint.setColor(color);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(dp(width));paint.setStrokeJoin(Paint.Join.ROUND);paint.setStrokeCap(Paint.Cap.ROUND);canvas.drawPath(path,paint);
        }
        @Override protected void onDraw(Canvas canvas){
            super.onDraw(canvas);left=dp(elevation?44:14);right=getWidth()-dp(14);top=dp(22);bottom=getHeight()-dp(elevation?26:12);
            if(right<=left||bottom<=top)return;
            paint.setStyle(Paint.Style.FILL);paint.setColor(palette.high);canvas.drawRoundRect(0,0,getWidth(),getHeight()-dp(3),dp(12),dp(12),paint);
            minHeight=Double.POSITIVE_INFINITY;maxHeight=Double.NEGATIVE_INFINITY;
            float minX=Float.POSITIVE_INFINITY,maxX=Float.NEGATIVE_INFINITY,minY=minX,maxY=maxX;
            for(double[] point:trace.nodes){minHeight=Math.min(minHeight,point[3]);maxHeight=Math.max(maxHeight,point[3]);if(Double.isFinite(point[1])){minX=Math.min(minX,(float)point[1]);maxX=Math.max(maxX,(float)point[1]);minY=Math.min(minY,(float)point[2]);maxY=Math.max(maxY,(float)point[2]);}}
            double range=Math.max(10,maxHeight-minHeight);minHeight-=range*.12;maxHeight+=range*.12;
            scale=Math.min((right-left)/Math.max(.000001f,maxX-minX),(bottom-top)/Math.max(.000001f,maxY-minY));
            offsetX=(left+right-(maxX-minX)*scale)/2-minX*scale;offsetY=(top+bottom-(maxY-minY)*scale)/2-minY*scale;
            paint.setColor(palette.muted);paint.setTextSize(dp(11));paint.setTextAlign(Paint.Align.LEFT);
            canvas.drawText(elevation?"Elevation · ft":"GPS route · N ↑",dp(10),dp(15),paint);
            if(elevation){
                canvas.drawText(String.format(Locale.getDefault(),"%.0f",maxHeight),dp(4),top+dp(9),paint);canvas.drawText(String.format(Locale.getDefault(),"%.0f",minHeight),dp(4),bottom,paint);
                canvas.drawText("0",left,getHeight()-dp(8),paint);paint.setTextAlign(Paint.Align.RIGHT);canvas.drawText(String.format(Locale.getDefault(),"%.1f %s",trace.distance/(miles?1609.344:1000),miles?"mi":"km"),right,getHeight()-dp(8),paint);
                int step=trace.step(selected);paint.setColor(palette.primaryContainer);canvas.drawRect(x(trace.point(trace.starts[step])),top,x(trace.point(trace.ends[step])),bottom,paint);
            }
            line(canvas,0,trace.distance,palette.outline,2);
            int step=trace.step(selected);line(canvas,trace.starts[step],trace.ends[step],palette.primary,3);
            double[] point=trace.point(selected);
            if(Double.isFinite(elevation?point[3]:point[1])){
                float x=x(point),y=y(point);if(elevation){paint.setColor(palette.primary);paint.setStrokeWidth(dp(1));canvas.drawLine(x,top,x,bottom,paint);}
                paint.setStyle(Paint.Style.FILL);paint.setColor(palette.container);canvas.drawCircle(x,y,dp(7),paint);paint.setColor(palette.primary);canvas.drawCircle(x,y,dp(4),paint);
            }
        }
        @Override public boolean onTouchEvent(MotionEvent event){
            if(!elevation)return super.onTouchEvent(event);
            int action=event.getActionMasked();
            if(action==MotionEvent.ACTION_DOWN||action==MotionEvent.ACTION_MOVE||action==MotionEvent.ACTION_UP){
                getParent().requestDisallowInterceptTouchEvent(action!=MotionEvent.ACTION_UP);select(trace.distance*Math.max(0,Math.min(1,(event.getX()-left)/Math.max(1,right-left))));
                if(action==MotionEvent.ACTION_UP)performClick();return true;
            }
            if(action==MotionEvent.ACTION_CANCEL){getParent().requestDisallowInterceptTouchEvent(false);return true;}
            return false;
        }
        @Override public boolean performClick(){super.performClick();return true;}
    }
}
