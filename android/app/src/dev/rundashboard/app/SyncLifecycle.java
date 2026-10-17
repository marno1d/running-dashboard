package dev.rundashboard.app;

/** Durable intent to finish a sync, distinct from a deliberate user pause. */
final class SyncLifecycle {
    boolean running, pending, userPaused, interrupted;
    long retryAfter;
    SyncLifecycle(boolean pending,long retryAfter){this.pending=pending;this.retryAfter=retryAfter;}
    boolean begin(){
        if(running)return false;
        running=true;pending=true;userPaused=false;interrupted=false;retryAfter=0;
        return true;
    }
    void pause(){userPaused=true;pending=false;retryAfter=0;}
    void interrupt(){interrupted=true;pending=!userPaused;}
    void finish(boolean succeeded,boolean servicePaused,long now){
        running=false;
        pending=!userPaused&&(interrupted||!succeeded||servicePaused);
        retryAfter=pending?now+300000:0;
    }
    boolean shouldResume(long now){return pending&&!running&&now>=retryAfter;}
}
