package dev.rundashboard.app;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.view.View;
import org.json.JSONArray;
import org.json.JSONObject;

/** A north-up outline with equal horizontal and vertical scales; no map service. */
final class RouteView extends View {
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private final MaterialPalette palette;
    private final boolean compact;
    private JSONArray segments=new JSONArray();
    private JSONArray track;
    private double highlight=Double.NaN;
    RouteView(Context context,MaterialPalette palette){
        this(context,palette,false);
    }
    RouteView(Context context,MaterialPalette palette,boolean compact){
        super(context);this.palette=palette;this.compact=compact;
        setContentDescription("GPS route outline, north at the top. Circle marks the start; square marks the finish.");
        setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);
    }
    boolean setRoute(JSONObject route){
        segments=route==null?null:route.optJSONArray("segments");invalidate();
        return segments!=null&&segments.length()>0;
    }
    void setTrack(JSONArray points){
        track=points;
        if(points!=null&&points.length()>1){
            JSONArray line=new JSONArray();
            for(int i=0;i<points.length();i++){
                JSONArray p=points.optJSONArray(i);if(p!=null)line.put(new JSONArray(java.util.Arrays.asList(p.optDouble(1),p.optDouble(2))));
            }
            segments=new JSONArray().put(line);
        }
        invalidate();
    }
    void setHighlight(double distance){
        highlight=distance;
        setContentDescription("GPS route outline, north at the top. Circle marks the start; triangle marks the selected course endpoint.");
        invalidate();
    }
    @Override protected void onDraw(Canvas canvas){
        super.onDraw(canvas);if(segments==null||segments.length()==0)return;
        float left=Float.POSITIVE_INFINITY,top=left,right=Float.NEGATIVE_INFINITY,bottom=right;
        for(int i=0;i<segments.length();i++){
            JSONArray segment=segments.optJSONArray(i);if(segment==null)continue;
            for(int j=0;j<segment.length();j++){
                JSONArray p=segment.optJSONArray(j);if(p==null)continue;
                float x=(float)p.optDouble(0),y=(float)p.optDouble(1);
                left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y);
            }
        }
        if(!Float.isFinite(left)||!Float.isFinite(top))return;
        float density=getResources().getDisplayMetrics().density,pad=(compact?8:18)*density;
        float scale=Math.min((getWidth()-2*pad)/Math.max(.000001f,right-left),(getHeight()-2*pad)/Math.max(.000001f,bottom-top));
        float offsetX=(getWidth()-(right-left)*scale)/2-left*scale,offsetY=(getHeight()-(bottom-top)*scale)/2-top*scale;
        float startX=0,startY=0,endX=0,endY=0;boolean started=false;
        paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth((compact?2:3)*density);paint.setStrokeCap(Paint.Cap.ROUND);paint.setStrokeJoin(Paint.Join.ROUND);paint.setColor(Double.isFinite(highlight)?palette.outline:palette.primary);
        for(int i=0;i<segments.length();i++){
            JSONArray segment=segments.optJSONArray(i);if(segment==null)continue;Path path=new Path();
            for(int j=0;j<segment.length();j++){
                JSONArray p=segment.optJSONArray(j);if(p==null)continue;
                float x=offsetX+(float)p.optDouble(0)*scale,y=offsetY+(float)p.optDouble(1)*scale;
                if(j==0)path.moveTo(x,y);else path.lineTo(x,y);
                if(!started){startX=x;startY=y;started=true;}endX=x;endY=y;
            }
            canvas.drawPath(path,paint);
        }
        if(!started)return;
        // A larger start ring remains visible when a loop finishes at the start.
        float startRadius=(compact?4:8)*density,endRadius=(compact?2:4)*density;
        paint.setStyle(Paint.Style.FILL);paint.setColor(palette.container);canvas.drawCircle(startX,startY,startRadius,paint);
        paint.setStyle(Paint.Style.STROKE);paint.setColor(palette.primary);paint.setStrokeWidth((compact?1.5f:2)*density);canvas.drawCircle(startX,startY,startRadius,paint);
        paint.setStyle(Paint.Style.FILL);canvas.drawRect(endX-endRadius,endY-endRadius,endX+endRadius,endY+endRadius,paint);
        if(Double.isFinite(highlight)&&track!=null&&track.length()>1){
            Path selected=new Path();float markerX=startX,markerY=startY;
            for(int i=0;i<track.length();i++){
                JSONArray p=track.optJSONArray(i);if(p==null)continue;
                double distance=p.optDouble(0),x=p.optDouble(1),y=p.optDouble(2);
                boolean stop=distance>=highlight;
                if(stop&&i>0){
                    JSONArray previous=track.optJSONArray(i-1);double before=previous.optDouble(0);
                    double fraction=Math.max(0,Math.min(1,(highlight-before)/Math.max(.001,distance-before)));
                    x=previous.optDouble(1)+(x-previous.optDouble(1))*fraction;y=previous.optDouble(2)+(y-previous.optDouble(2))*fraction;
                }
                markerX=offsetX+(float)x*scale;markerY=offsetY+(float)y*scale;
                if(i==0)selected.moveTo(markerX,markerY);else selected.lineTo(markerX,markerY);
                if(stop)break;
            }
            paint.setColor(palette.primary);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(4*density);canvas.drawPath(selected,paint);
            float radius=9*density;Path marker=new Path();marker.moveTo(markerX,markerY-radius);marker.lineTo(markerX-radius,markerY+radius);marker.lineTo(markerX+radius,markerY+radius);marker.close();
            paint.setStyle(Paint.Style.FILL);paint.setColor(palette.container);canvas.drawPath(marker,paint);
            paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(2*density);paint.setColor(palette.primary);canvas.drawPath(marker,paint);
        }
    }
}
