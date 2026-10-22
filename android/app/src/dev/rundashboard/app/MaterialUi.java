package dev.rundashboard.app;

import android.content.Context;
import android.content.res.ColorStateList;
import android.content.res.Configuration;
import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.util.ArrayList;

/** Framework-native components styled with shared Material roles, shapes and interaction states. */
final class MaterialUi {
    static boolean isDark(Context context){
        String mode=context.getSharedPreferences("training",0).getString("appearance","system");
        return "dark".equals(mode)||"system".equals(mode)
            &&(context.getResources().getConfiguration().uiMode&Configuration.UI_MODE_NIGHT_MASK)==Configuration.UI_MODE_NIGHT_YES;
    }
    static MaterialPalette palette(Context context){return new MaterialPalette(isDark(context));}
    static int dp(Context context,int value){return Math.round(value*context.getResources().getDisplayMetrics().density);}
    static GradientDrawable shape(Context context,int color,int radius){
        GradientDrawable result=new GradientDrawable();result.setColor(color);result.setCornerRadius(dp(context,radius));return result;
    }
    static Drawable ripple(Context context,int color,int radius,int rippleColor){
        return new RippleDrawable(ColorStateList.valueOf((rippleColor&0x00ffffff)|0x24000000),shape(context,color,radius),shape(context,0xffffffff,radius));
    }
    /** Wraps chips or stacks equal-width actions whenever their actual labels need more room. */
    static class ButtonGroup extends ViewGroup {
        private final boolean equal;
        private final int gap;
        private final ArrayList<View> visible=new ArrayList<>();
        private ButtonLayout.Plan plan;
        ButtonGroup(Context context,boolean equal){super(context);this.equal=equal;gap=dp(context,8);}
        protected int[] childWidths(int available,int[] preferred,int gap){return ButtonLayout.widths(available,preferred,gap,equal);}
        @Override protected ViewGroup.LayoutParams generateDefaultLayoutParams(){return new ViewGroup.LayoutParams(-2,-2);}
        @Override protected void onMeasure(int widthSpec,int heightSpec){
            visible.clear();int natural=0;
            for(int i=0;i<getChildCount();i++){
                View child=getChildAt(i);if(child.getVisibility()==GONE)continue;visible.add(child);
                child.measure(MeasureSpec.makeMeasureSpec(0,MeasureSpec.UNSPECIFIED),MeasureSpec.makeMeasureSpec(0,MeasureSpec.UNSPECIFIED));
                natural+=child.getMeasuredWidth();
            }
            if(visible.size()>1)natural+=gap*(visible.size()-1);
            int padding=getPaddingLeft()+getPaddingRight();
            int width=MeasureSpec.getMode(widthSpec)==MeasureSpec.UNSPECIFIED?natural+padding:MeasureSpec.getSize(widthSpec);
            int available=Math.max(0,width-padding);
            int[] preferred=new int[visible.size()],heights=new int[visible.size()];
            for(int i=0;i<preferred.length;i++)preferred[i]=visible.get(i).getMeasuredWidth();
            int[] widths=childWidths(available,preferred,gap);
            for(int i=0;i<widths.length;i++){
                View child=visible.get(i);child.measure(MeasureSpec.makeMeasureSpec(widths[i],MeasureSpec.EXACTLY),MeasureSpec.makeMeasureSpec(0,MeasureSpec.UNSPECIFIED));heights[i]=child.getMeasuredHeight();
            }
            plan=ButtonLayout.place(available,widths,heights,gap);
            setMeasuredDimension(resolveSize(width,widthSpec),resolveSize(plan.height+getPaddingTop()+getPaddingBottom(),heightSpec));
        }
        @Override protected void onLayout(boolean changed,int left,int top,int right,int bottom){
            if(plan==null)return;
            boolean rtl=getLayoutDirection()==LAYOUT_DIRECTION_RTL;
            for(int i=0;i<visible.size();i++){
                View child=visible.get(i);int x=rtl?getWidth()-getPaddingRight()-plan.left[i]-child.getMeasuredWidth():getPaddingLeft()+plan.left[i];
                int y=getPaddingTop()+plan.top[i];child.layout(x,y,x+child.getMeasuredWidth(),y+child.getMeasuredHeight());
            }
        }
    }
    static final class MetricGroup extends ButtonGroup {
        private int shadedFrom=-1,shadeColor;
        private final Paint shade=new Paint(Paint.ANTI_ALIAS_FLAG);
        MetricGroup(Context context){super(context,true);}
        void shadeFrom(int firstChild,int color){shadedFrom=firstChild;shadeColor=color;invalidate();}
        @Override protected int[] childWidths(int available,int[] preferred,int gap){return ButtonLayout.metricWidths(available,preferred,gap);}
        @Override protected void dispatchDraw(Canvas canvas){
            if(shadedFrom>=0&&shadedFrom<getChildCount()){
                int top=getHeight(),bottom=0;
                for(int i=shadedFrom;i<getChildCount();i++){
                    View child=getChildAt(i);if(child.getVisibility()==GONE)continue;
                    top=Math.min(top,child.getTop());bottom=Math.max(bottom,child.getBottom());
                }
                if(bottom>top){shade.setColor(shadeColor);float radius=dp(getContext(),6);canvas.drawRoundRect(0,top,getWidth(),bottom,radius,radius,shade);}
            }
            super.dispatchDraw(canvas);
        }
    }
    static final class NavigationItem extends LinearLayout {
        private final ImageView icon;
        private final TextView label;
        private final MaterialPalette palette;
        private final String name;
        private final int glyph;
        NavigationItem(Context context,String name,int glyph,MaterialPalette palette){
            super(context);this.name=name;this.glyph=glyph;this.palette=palette;
            setOrientation(VERTICAL);setGravity(Gravity.CENTER);setPadding(0,dp(context,10),0,dp(context,8));
            setMinimumHeight(dp(context,72));setFocusable(true);setClickable(true);
            setBackground(ripple(context,palette.container,24,palette.primary));
            icon=new ImageView(context);icon.setPadding(dp(context,20),dp(context,4),dp(context,20),dp(context,4));
            icon.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
            addView(icon,new LinearLayout.LayoutParams(dp(context,64),dp(context,32)));
            label=new TextView(context);label.setText(name);label.setTextSize(12);label.setGravity(Gravity.CENTER);
            label.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
            LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(context,4);addView(label,lp);
            setContentDescription(name);setActive(false);
        }
        void setActive(boolean selected){
            setSelected(selected);icon.setBackground(shape(getContext(),selected?palette.primaryContainer:palette.container,16));
            icon.setImageDrawable(new Icon(glyph,selected?palette.onPrimaryContainer:palette.muted));
            label.setTextColor(selected?palette.ink:palette.muted);
            label.setTypeface(android.graphics.Typeface.create("sans-serif",selected?1:0));
            setContentDescription(name);
        }
        @Override protected void onMeasure(int widthSpec,int heightSpec){
            if(MeasureSpec.getMode(widthSpec)!=MeasureSpec.UNSPECIFIED){
                int width=Math.min(dp(getContext(),64),Math.max(dp(getContext(),24),MeasureSpec.getSize(widthSpec)-dp(getContext(),8)));
                icon.getLayoutParams().width=width;int horizontal=Math.max(0,(width-dp(getContext(),24))/2);
                icon.setPadding(horizontal,dp(getContext(),4),horizontal,dp(getContext(),4));
            }
            super.onMeasure(widthSpec,heightSpec);
        }
        @Override public void onInitializeAccessibilityNodeInfo(AccessibilityNodeInfo info){
            super.onInitializeAccessibilityNodeInfo(info);info.setClassName("android.widget.Button");info.setSelected(isSelected());
        }
    }
    /** Legend symbols use the same shapes and colors as chart points. */
    static final class Marker extends Drawable {
        private final int kind;
        private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        Marker(int kind,int color){this.kind=kind;paint.setColor(color);paint.setStrokeWidth(1.8f);}
        @Override public void draw(Canvas canvas){
            canvas.save();canvas.translate(getBounds().left,getBounds().top);canvas.scale(getBounds().width()/14f,getBounds().height()/14f);
            paint.setStyle(kind==1?Paint.Style.STROKE:Paint.Style.FILL);
            if(kind==2||kind==4){Path shape=new Path();shape.moveTo(7,2);shape.lineTo(12,kind==2?7:12);if(kind==2)shape.lineTo(7,12);shape.lineTo(2,kind==2?7:12);shape.close();canvas.drawPath(shape,paint);}
            else if(kind==3)canvas.drawRect(3,3,11,11,paint);
            else canvas.drawCircle(7,7,4.5f,paint);
            canvas.restore();
        }
        @Override public void setAlpha(int alpha){paint.setAlpha(alpha);invalidateSelf();}
        @Override public void setColorFilter(ColorFilter filter){paint.setColorFilter(filter);invalidateSelf();}
        @Override public int getOpacity(){return PixelFormat.TRANSLUCENT;}
    }
    /** Simple 24dp outline icons, avoiding font glyph/emoji differences across devices. */
    static final class Icon extends Drawable {
        static final int TRENDS=0,SESSIONS=1,TARGETS=2,PROFILE=3,SYNC=4,BACK=5,MORE=6,CLOSE=7;
        private final int kind;
        private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        Icon(int kind,int color){this.kind=kind;paint.setColor(color);paint.setStrokeWidth(1.8f);paint.setStrokeCap(Paint.Cap.ROUND);paint.setStrokeJoin(Paint.Join.ROUND);}
        private void line(Canvas canvas,float... points){Path path=new Path();path.moveTo(points[0],points[1]);for(int i=2;i<points.length;i+=2)path.lineTo(points[i],points[i+1]);canvas.drawPath(path,paint);}
        @Override public void draw(Canvas canvas){
            canvas.save();canvas.translate(getBounds().left,getBounds().top);canvas.scale(getBounds().width()/24f,getBounds().height()/24f);paint.setStyle(Paint.Style.STROKE);
            switch(kind){
                case TRENDS:line(canvas,4,19,4,5);line(canvas,4,19,21,19);line(canvas,7,15,11,10,15,13,21,5);break;
                case SESSIONS:canvas.drawRoundRect(4,3,20,21,3,3,paint);line(canvas,8,8,16,8);line(canvas,8,12,16,12);line(canvas,8,16,13,16);break;
                case TARGETS:canvas.drawCircle(12,12,8,paint);canvas.drawCircle(12,12,4,paint);canvas.drawCircle(12,12,1,paint);break;
                case PROFILE:canvas.drawCircle(12,8,4,paint);canvas.drawArc(4,14,20,27,190,160,false,paint);break;
                case SYNC:canvas.drawArc(4,4,20,20,35,250,false,paint);line(canvas,18,4,20,9,15,8);break;
                case BACK:line(canvas,14,5,7,12,14,19);line(canvas,7,12,21,12);break;
                case CLOSE:line(canvas,6,6,18,18);line(canvas,18,6,6,18);break;
                case MORE:paint.setStyle(Paint.Style.FILL);canvas.drawCircle(12,5,1.6f,paint);canvas.drawCircle(12,12,1.6f,paint);canvas.drawCircle(12,19,1.6f,paint);break;
            }
            canvas.restore();
        }
        @Override public void setAlpha(int alpha){paint.setAlpha(alpha);invalidateSelf();}
        @Override public void setColorFilter(ColorFilter filter){paint.setColorFilter(filter);invalidateSelf();}
        @Override public int getOpacity(){return PixelFormat.TRANSLUCENT;}
    }
}
