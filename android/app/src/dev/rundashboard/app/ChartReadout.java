package dev.rundashboard.app;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.text.TextUtils;

/** A bounded value bubble in a reserved header, shared by both chart renderers. */
final class ChartReadout {
    static int reservedHeight(Context context){
        Paint paint=new Paint();paint.setTypeface(android.graphics.Typeface.create("sans-serif",0));
        paint.setTextSize(android.util.TypedValue.applyDimension(android.util.TypedValue.COMPLEX_UNIT_SP,12,context.getResources().getDisplayMetrics()));
        float density=context.getResources().getDisplayMetrics().density;
        return (int)Math.ceil(2*(paint.descent()-paint.ascent())+36*density);
    }
    static void draw(Canvas canvas,Paint paint,MaterialPalette palette,float density,float textSize,
                     float width,float x,String heading,String value){
        paint.setStyle(Paint.Style.FILL);paint.setAlpha(255);paint.setPathEffect(null);
        paint.setTypeface(android.graphics.Typeface.create("sans-serif",0));paint.setTextSize(textSize);
        float pad=10*density,gap=4*density,line=paint.descent()-paint.ascent();
        float available=Math.max(1,width-4*density-2*pad);
        // Draw both lines within the view even with enlarged system fonts.
        heading=TextUtils.ellipsize(heading,new android.text.TextPaint(paint),available,TextUtils.TruncateAt.END).toString();
        value=TextUtils.ellipsize(value,new android.text.TextPaint(paint),available,TextUtils.TruncateAt.END).toString();
        float bubbleWidth=Math.min(width-4*density,Math.max(paint.measureText(heading),paint.measureText(value))+2*pad);
        float bubbleHeight=2*line+gap+2*pad;
        float left=Math.max(2*density,Math.min(width-2*density-bubbleWidth,x-bubbleWidth/2));
        float top=2*density;
        RectF bubble=new RectF(left,top,left+bubbleWidth,top+bubbleHeight);
        paint.setColor(palette.high);canvas.drawRoundRect(bubble,10*density,10*density,paint);
        paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(density);paint.setColor(palette.outline);canvas.drawRoundRect(bubble,10*density,10*density,paint);paint.setStyle(Paint.Style.FILL);
        float baseline=top+pad-paint.ascent();paint.setColor(palette.muted);canvas.drawText(heading,left+pad,baseline,paint);
        paint.setColor(palette.ink);canvas.drawText(value,left+pad,baseline+line+gap,paint);
    }
}
