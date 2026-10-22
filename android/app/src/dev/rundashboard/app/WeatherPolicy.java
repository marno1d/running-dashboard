package dev.rundashboard.app;

/** Refresh timing and a persisted one-hour hold after manual weather edits. */
final class WeatherPolicy {
    static final long HOUR=60*60*1000L,REFRESH=10*60*1000L;
    static boolean held(long now,long manualUntil){return manualUntil>now;}
    static boolean shouldRefresh(long now,long manualUntil,long lastFetch,long lastAttempt){
        // Failed and manual requests also consume the automatic cooldown.
        // A clock rollback must not accidentally permit extra automatic requests.
        return !held(now,manualUntil)&&(lastFetch<=0||now-lastFetch>=REFRESH)
            &&(lastAttempt<=0||now-lastAttempt>=REFRESH);
    }
    static boolean shouldRequest(boolean manual,long now,long manualUntil,long lastFetch,long lastAttempt){
        return manual||shouldRefresh(now,manualUntil,lastFetch,lastAttempt);
    }
}
