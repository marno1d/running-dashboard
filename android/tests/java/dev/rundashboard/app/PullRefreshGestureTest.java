package dev.rundashboard.app;

public final class PullRefreshGestureTest {
    private static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    public static void main(String[] args){
        for(int density:new int[]{1,2,3}){
            float slop=8*density,threshold=64*density;
            PullRefreshGesture gesture=new PullRefreshGesture(slop,threshold);
            float full=slop+threshold*2;
            gesture.begin(0,0,false);
            check(!gesture.move(0,full*2),"not at top or disabled: leave scrolling alone");
            check(!gesture.release(false,true),"a gesture started below the top must never refresh");

            gesture.begin(0,0,true);
            check(!gesture.move(2*density,slop),"touch jitter must not capture a tap");
            check(gesture.move(2*density,full-1),"downward pull owns the gesture");
            check(!gesture.ready(),"below threshold");
            check(!gesture.release(false,true),"short pull cancels");

            gesture.begin(10,20,true);
            check(gesture.move(10,20+full),"full downward pull");
            check(gesture.ready(),"at threshold is armed");
            check(gesture.release(false,true),"release triggers refresh");
            check(!gesture.release(false,true),"the same release cannot refresh twice");
            check(!gesture.move(10,20+full*2),"a finished gesture cannot re-arm itself");

            gesture.begin(0,0,true);gesture.move(0,full*2);
            check(!gesture.release(true,true),"Android cancellation must not refresh");
            gesture.begin(0,0,true);gesture.move(0,full*2);
            check(!gesture.release(false,false),"sync starting, sign-out or leaving top mid-pull cancels refresh");
            gesture.begin(0,0,false);gesture.move(0,full*2);
            check(!gesture.release(false,false),"pulls while busy cannot queue a second sync");

            gesture.begin(0,0,true);gesture.move(0,full*2);gesture.cancel();
            check(!gesture.move(0,full*3),"multi-touch cancellation prevents later re-arming");
            check(!gesture.release(false,true),"cancelled multi-touch never refreshes");

            gesture.begin(0,0,true);
            check(!gesture.move(full,slop+1),"horizontal chart or chip gesture stays with its child");
            check(!gesture.move(full,full*3),"initial horizontal direction stays locked");
            check(!gesture.release(false,true),"horizontal gesture never refreshes");
            gesture.begin(0,0,true);gesture.move(0,-full);
            check(!gesture.move(0,full*3),"initial upward scrolling stays locked");
            check(!gesture.release(false,true),"scroll reversal never refreshes");

            gesture.begin(0,0,true);gesture.move(0,full*2);
            check(gesture.ready(),"long pull armed");
            gesture.move(0,slop+2);
            check(!gesture.ready(),"dragging back below threshold disarms refresh");
            check(!gesture.release(false,true),"retreat then release cancels");
            gesture.begin(0,0,true);gesture.move(0,full*2);gesture.move(0,-full);
            check(gesture.distance()==0,"indicator cannot move backwards beyond its resting position");
            check(!gesture.release(false,true),"upward retreat cancels");
        }
        System.out.println("Pull-to-refresh: top-only, threshold/release, cancellation, direction locking, densities and duplicate prevention: OK");
    }
}
