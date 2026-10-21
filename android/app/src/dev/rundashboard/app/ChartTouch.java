package dev.rundashboard.app;

import android.view.GestureDetector;
import android.view.MotionEvent;
import android.view.ScaleGestureDetector;
import android.view.View;
import android.view.ViewConfiguration;

/** Shared chart gestures: horizontal scrubbing, vertical page scroll, two-finger navigation. */
final class ChartTouch {
    interface Listener {
        void scrub(float x,float y);
        void finish();
        void tap(float x,float y);
        void zoom(float factor,float x,float y);
        void pan(float dx,float dy);
        void reset();
    }
    private final View view;
    private final Listener listener;
    private final int slop;
    private final ScaleGestureDetector scale;
    private final GestureDetector taps;
    private boolean exploration=true,scrubbing,multi,ceded;
    private float downX,downY,focusX,focusY;

    ChartTouch(View view,Listener listener){
        this.view=view;this.listener=listener;slop=ViewConfiguration.get(view.getContext()).getScaledTouchSlop();
        scale=new ScaleGestureDetector(view.getContext(),new ScaleGestureDetector.SimpleOnScaleGestureListener(){
            public boolean onScaleBegin(ScaleGestureDetector detector){return true;}
            public boolean onScale(ScaleGestureDetector detector){listener.zoom(detector.getScaleFactor(),detector.getFocusX(),detector.getFocusY());return true;}
        });scale.setQuickScaleEnabled(false);
        taps=new GestureDetector(view.getContext(),new GestureDetector.SimpleOnGestureListener(){
            public boolean onDown(MotionEvent event){return true;}
            public boolean onSingleTapConfirmed(MotionEvent event){listener.tap(event.getX(),event.getY());return true;}
            public boolean onDoubleTap(MotionEvent event){if(exploration)listener.reset();return true;}
        });taps.setIsLongpressEnabled(false);
    }
    void setExplorationEnabled(boolean value){exploration=value;}
    private void own(boolean value){if(view.getParent()!=null)view.getParent().requestDisallowInterceptTouchEvent(value);}
    private void cancelTaps(MotionEvent event){MotionEvent cancel=MotionEvent.obtain(event);cancel.setAction(MotionEvent.ACTION_CANCEL);taps.onTouchEvent(cancel);cancel.recycle();}
    private void focus(MotionEvent event,int skip){
        float x=0,y=0;int count=0;
        for(int i=0;i<event.getPointerCount();i++)if(i!=skip){x+=event.getX(i);y+=event.getY(i);count++;}
        if(count>0){focusX=x/count;focusY=y/count;}
    }
    boolean onTouchEvent(MotionEvent event){
        int action=event.getActionMasked();
        if(action==MotionEvent.ACTION_DOWN){downX=event.getX();downY=event.getY();scrubbing=multi=ceded=false;}
        if(action==MotionEvent.ACTION_CANCEL){cancelTaps(event);if(exploration)scale.onTouchEvent(event);if(scrubbing)listener.finish();own(false);return true;}
        if(ceded)return false;
        if(action==MotionEvent.ACTION_POINTER_DOWN){
            multi=true;cancelTaps(event);if(scrubbing){listener.finish();scrubbing=false;}
            if(!exploration){ceded=true;own(false);return false;}
            own(true);focus(event,-1);
        }
        if(exploration)scale.onTouchEvent(event);
        if(multi){
            if(action==MotionEvent.ACTION_MOVE&&event.getPointerCount()>1){
                float previousX=focusX,previousY=focusY;focus(event,-1);
                listener.pan(focusX-previousX,focusY-previousY);
            }else if(action==MotionEvent.ACTION_POINTER_UP)focus(event,event.getActionIndex());
            if(action==MotionEvent.ACTION_UP)own(false);
            return true; // Lifting one of two fingers must never begin a scrub or tap.
        }
        if(action==MotionEvent.ACTION_MOVE){
            int direction=ChartInteraction.direction(event.getX()-downX,event.getY()-downY,slop);
            if(!scrubbing&&direction<0){ceded=true;cancelTaps(event);own(false);return false;}
            if(!scrubbing&&direction>0){scrubbing=true;cancelTaps(event);own(true);}
            if(scrubbing){listener.scrub(event.getX(),event.getY());return true;}
        }
        if(action==MotionEvent.ACTION_UP&&scrubbing){listener.scrub(event.getX(),event.getY());listener.finish();own(false);return true;}
        taps.onTouchEvent(event);
        if(action==MotionEvent.ACTION_UP)own(false);
        return true;
    }
}
