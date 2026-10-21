package dev.rundashboard.app;

/** Direction locking and release-to-refresh decisions, independent of Android views. */
final class PullRefreshGesture {
    private final float slop,threshold;
    private float startX,startY;
    private boolean tracking,dragging;
    private float distance;

    PullRefreshGesture(float slop,float threshold){this.slop=slop;this.threshold=threshold;}
    void begin(float x,float y,boolean allowedAtTop){
        cancel();startX=x;startY=y;tracking=allowedAtTop;
    }
    boolean move(float x,float y){
        if(!tracking)return false;
        float dx=x-startX,dy=y-startY;
        if(!dragging){
            if(Math.max(Math.abs(dx),Math.abs(dy))<=slop)return false;
            // Lock the initial direction so horizontal charts and upward scrolls stay with their child.
            if(dy<=slop||dy<=Math.abs(dx)*1.2f){cancel();return false;}
            dragging=true;
        }
        distance=Math.max(0,(dy-slop)*.5f);
        return true;
    }
    boolean dragging(){return dragging;}
    float distance(){return distance;}
    boolean ready(){return dragging&&distance>=threshold;}
    boolean release(boolean cancelled,boolean stillAllowed){
        boolean refresh=!cancelled&&stillAllowed&&ready();cancel();return refresh;
    }
    void cancel(){tracking=false;dragging=false;distance=0;}
}
