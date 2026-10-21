package dev.rundashboard.app;

import android.content.Context;
import android.content.res.ColorStateList;
import android.view.Gravity;
import android.view.HapticFeedbackConstants;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.ProgressBar;
import android.widget.ScrollView;

/** Pull-to-refresh around the main scroller; ordinary scrolling stays with ScrollView. */
final class PullRefreshLayout extends FrameLayout {
    private final ScrollView scroll;
    private final Runnable onRefresh;
    private final PullRefreshGesture gesture;
    private final FrameLayout indicator;
    private final ImageView arrow;
    private final ProgressBar spinner;
    private boolean refreshEnabled,refreshing,ownsGesture,armed;

    PullRefreshLayout(Context context,ScrollView scroll,Runnable onRefresh){
        super(context);this.scroll=scroll;this.onRefresh=onRefresh;
        MaterialPalette palette=MaterialUi.palette(context);
        gesture=new PullRefreshGesture(ViewConfiguration.get(context).getScaledTouchSlop(),dp(64));
        addView(scroll,new FrameLayout.LayoutParams(-1,-1));
        indicator=new FrameLayout(context);indicator.setBackground(MaterialUi.shape(context,palette.container,20));indicator.setElevation(dp(6));
        indicator.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);
        arrow=new ImageView(context);arrow.setImageDrawable(new MaterialUi.Icon(MaterialUi.Icon.SYNC,palette.primary));
        FrameLayout.LayoutParams glyph=new FrameLayout.LayoutParams(dp(24),dp(24),Gravity.CENTER);indicator.addView(arrow,glyph);
        spinner=new ProgressBar(context,null,android.R.attr.progressBarStyleSmall);spinner.setIndeterminate(true);spinner.setIndeterminateTintList(ColorStateList.valueOf(palette.primary));
        indicator.addView(spinner,new FrameLayout.LayoutParams(dp(24),dp(24),Gravity.CENTER));spinner.setVisibility(GONE);
        addView(indicator,new FrameLayout.LayoutParams(dp(40),dp(40),Gravity.TOP|Gravity.CENTER_HORIZONTAL));indicator.setVisibility(GONE);
    }
    private int dp(int value){return MaterialUi.dp(getContext(),value);}
    private boolean atTop(){return !scroll.canScrollVertically(-1);}
    void setRefreshEnabled(boolean enabled){
        refreshEnabled=enabled;
        if(!enabled){gesture.cancel();armed=false;if(!refreshing)hideIndicator();}
    }
    void setRefreshing(boolean running){
        if(refreshing==running)return;
        refreshing=running;gesture.cancel();armed=false;
        if(running){
            indicator.animate().cancel();indicator.setVisibility(VISIBLE);indicator.setAlpha(1);indicator.setScaleX(1);indicator.setScaleY(1);
            arrow.setVisibility(GONE);spinner.setVisibility(VISIBLE);
            indicator.animate().translationY(dp(24)).setDuration(180).start();
        }else hideIndicator();
    }
    private void showPull(){
        indicator.animate().cancel();spinner.setVisibility(GONE);arrow.setVisibility(VISIBLE);indicator.setVisibility(VISIBLE);
        float fraction=Math.min(1,gesture.distance()/dp(64));
        indicator.setTranslationY(Math.min(dp(96),gesture.distance())-dp(40));indicator.setAlpha(.3f+.7f*fraction);
        float scale=Math.min(1,gesture.distance()/dp(32));indicator.setScaleX(scale);indicator.setScaleY(scale);arrow.setRotation(fraction*240);
        if(gesture.ready()!=armed){armed=gesture.ready();if(armed){performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK);announceForAccessibility("Release to sync");}}
    }
    private void hideIndicator(){
        indicator.animate().cancel();
        if(indicator.getVisibility()!=VISIBLE)return;
        indicator.animate().alpha(0).translationY(-dp(48)).setDuration(160).withEndAction(()->{
            if(!refreshing&&!gesture.dragging()){indicator.setVisibility(GONE);spinner.setVisibility(GONE);}
        }).start();
    }
    private void cancelPull(){gesture.cancel();armed=false;if(!refreshing)hideIndicator();}
    @Override public boolean onInterceptTouchEvent(MotionEvent event){
        int action=event.getActionMasked();
        if(action==MotionEvent.ACTION_DOWN){
            ownsGesture=false;armed=false;gesture.begin(event.getX(),event.getY(),refreshEnabled&&!refreshing&&atTop());return false;
        }
        if(!refreshEnabled||refreshing||event.getPointerCount()>1){cancelPull();return false;}
        if(action==MotionEvent.ACTION_MOVE){
            if(!atTop()){cancelPull();return false;}
            if(gesture.move(event.getX(),event.getY())){
                ownsGesture=true;showPull();getParent().requestDisallowInterceptTouchEvent(true);return true;
            }
        }else if(action==MotionEvent.ACTION_UP||action==MotionEvent.ACTION_CANCEL)cancelPull();
        return false;
    }
    @Override public boolean onTouchEvent(MotionEvent event){
        int action=event.getActionMasked();
        if(action==MotionEvent.ACTION_DOWN){
            ownsGesture=refreshEnabled&&!refreshing&&atTop();gesture.begin(event.getX(),event.getY(),ownsGesture);return ownsGesture;
        }
        if(!ownsGesture)return false;
        if(!refreshEnabled||refreshing||event.getPointerCount()>1)cancelPull();
        if(action==MotionEvent.ACTION_MOVE&&gesture.move(event.getX(),event.getY()))showPull();
        if(action==MotionEvent.ACTION_UP||action==MotionEvent.ACTION_CANCEL){
            boolean refresh=gesture.release(action==MotionEvent.ACTION_CANCEL,refreshEnabled&&!refreshing&&atTop());
            ownsGesture=false;armed=false;getParent().requestDisallowInterceptTouchEvent(false);
            if(refresh){performClick();onRefresh.run();}
            if(!refreshing)hideIndicator();
        }
        return true;
    }
    @Override public void requestDisallowInterceptTouchEvent(boolean disallow){
        if(disallow&&!ownsGesture)cancelPull();super.requestDisallowInterceptTouchEvent(disallow);
    }
    @Override protected void onDetachedFromWindow(){
        indicator.animate().cancel();gesture.cancel();ownsGesture=false;super.onDetachedFromWindow();
    }
    @Override public boolean performClick(){super.performClick();return true;}
}
