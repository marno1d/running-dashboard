package dev.rundashboard.app;

public final class SyncLifecycleTest {
    private static void check(boolean value,String label){if(!value)throw new AssertionError(label);}
    public static void main(String[] args){
        SyncLifecycle first=new SyncLifecycle(false,0);
        check(first.begin(),"first start");
        check(!first.begin(),"duplicate start is rejected");
        check(!first.shouldResume(1000),"active sync is not resumed twice");
        SyncLifecycle killed=new SyncLifecycle(first.pending,first.retryAfter);
        check(killed.shouldResume(1000),"process death restores unfinished work immediately");
        killed.begin();killed.finish(true,false,2000);
        check(!killed.pending&&!killed.shouldResume(Long.MAX_VALUE),"successful work stays completed");

        SyncLifecycle paused=new SyncLifecycle(false,0);
        paused.begin();paused.pause();paused.interrupt();paused.finish(true,true,3000);
        check(!paused.pending,"user pause wins over interruption and backend paused result");
        check(!new SyncLifecycle(paused.pending,paused.retryAfter).shouldResume(Long.MAX_VALUE),"pause survives process death");
        check(paused.begin(),"explicit resume after pause");
        check(paused.pending&&!paused.userPaused,"explicit resume persists work again");

        SyncLifecycle interrupted=new SyncLifecycle(false,0);
        interrupted.begin();interrupted.interrupt();interrupted.finish(true,false,4000);
        check(interrupted.pending,"late success cannot erase a service interruption");
        check(!interrupted.shouldResume(4001),"failure cooldown prevents repeated immediate requests");
        SyncLifecycle reopened=new SyncLifecycle(interrupted.pending,interrupted.retryAfter);
        check(!reopened.shouldResume(4001),"cooldown survives process death");
        check(reopened.shouldResume(304000),"interrupted work can resume after cooldown");

        SyncLifecycle limited=new SyncLifecycle(false,0);
        limited.begin();limited.finish(true,true,5000);
        check(limited.pending,"Garmin pause leaves work resumable");
        SyncLifecycle failed=new SyncLifecycle(false,0);
        failed.begin();failed.finish(false,false,6000);
        check(failed.pending,"request failure leaves work resumable");
        System.out.println("Sync duplicate prevention, process restart, user pause and retry cooldown: OK");
    }
}
