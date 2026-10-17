package dev.rundashboard.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Locale;
import org.json.JSONObject;

/** User-started downloads survive Activity destruction; a killed process resumes on reopen. */
public final class SyncService extends Service {
    private static final String CHANNEL="dashboard-sync", PAUSE="dev.rundashboard.app.PAUSE_SYNC";
    private static final int NOTIFICATION=41;
    private static final Handler MAIN=new Handler(Looper.getMainLooper());
    private static final ArrayList<Listener> LISTENERS=new ArrayList<>();
    private static Run active;
    private static volatile Snapshot latest;
    private static long nextId;
    private Run owned;
    private PowerManager.WakeLock wakeLock;
    private long lastNotification;
    private final Runnable deadline=()->interrupt();

    interface Listener {void changed(Snapshot state);}
    static final class Snapshot {
        final long id;
        final boolean running;
        final String label,error,operation;
        final int completed,total;
        final JSONObject result;
        Snapshot(Run run,boolean running,String label,int completed,int total,JSONObject result,String error){
            id=run.id;operation=run.operation;this.running=running;this.label=label;
            this.completed=completed;this.total=total;this.result=result;this.error=error;
        }
    }
    private static final class Run {
        final long id=++nextId;
        final String operation,today,settings;
        final int days;
        final SyncLifecycle lifecycle=new SyncLifecycle(false,0);
        volatile boolean cancelled;
        Run(String operation,int days,String settings){
            this.operation=operation;this.days=days;this.settings=settings;
            today=LocalDate.now().toString();lifecycle.begin();
        }
    }
    private static SharedPreferences prefs(Context context){return context.getSharedPreferences("sync_work",0);}
    static boolean isRunning(){return active!=null;}
    static boolean hasRequestedSync(Context context){return prefs(context).contains("operation");}
    static long completedId(){return latest!=null&&!latest.running?latest.id:0;}
    static void listen(Listener listener){if(!LISTENERS.contains(listener))LISTENERS.add(listener);if(latest!=null)listener.changed(latest);}
    static void unlisten(Listener listener){LISTENERS.remove(listener);}
    private static void publish(Snapshot state){
        latest=state;
        for(Listener listener:new ArrayList<>(LISTENERS))listener.changed(state);
    }
    private static void save(Context context,Run run){
        prefs(context).edit().putBoolean("pending",run.lifecycle.pending)
            .putLong("retry_after",run.lifecycle.retryAfter).putString("operation",run.operation)
            .putInt("days",run.days).putString("settings",run.settings).commit();
    }
    static void clear(Context context){prefs(context).edit().clear().commit();latest=null;}
    static void remember(Context context,String operation,int days,String settings){
        prefs(context).edit().putBoolean("pending",true).putLong("retry_after",0)
            .putString("operation",operation).putInt("days",days).putString("settings",settings).commit();
    }
    static boolean canResume(Context context){
        SharedPreferences saved=prefs(context);
        SyncLifecycle lifecycle=new SyncLifecycle(saved.getBoolean("pending",false),saved.getLong("retry_after",0));
        return !isRunning()&&lifecycle.shouldResume(System.currentTimeMillis());
    }
    static boolean resume(Context context,int days,String settings) throws Exception {
        if(!canResume(context))return false;
        SharedPreferences saved=prefs(context);
        String operation=saved.getString("operation","dashboard");
        // Respect edits made after a failed sync, including disabling terrain.
        if("sync_terrain".equals(operation)&&!new JSONObject(settings).optBoolean("include_terrain")){
            saved.edit().putBoolean("pending",false).commit();return false;
        }
        return start(context,operation,days,settings);
    }
    static boolean start(Context context,String operation,int days,String settings){
        if(active!=null)return false;
        if(!"dashboard".equals(operation)&&!"sync_terrain".equals(operation))throw new IllegalArgumentException("Unknown sync");
        Run run=new Run(operation,days,settings);save(context,run);active=run;
        try{
            context.startForegroundService(new Intent(context,SyncService.class));
            publish(new Snapshot(run,true,"Starting sync…",0,0,null,null));
            return true;
        }catch(RuntimeException error){
            active=null;run.lifecycle.interrupt();run.lifecycle.finish(false,true,System.currentTimeMillis());save(context,run);
            publish(new Snapshot(run,false,"Sync saved for later",0,0,null,"Couldn't start background sync. Reopen the app to resume."));
            return false;
        }
    }
    static void pause(Context context){
        Run run=active;
        if(run==null){prefs(context).edit().putBoolean("pending",false).commit();return;}
        run.lifecycle.pause();save(context,run);run.cancelled=true;
        publish(new Snapshot(run,true,"Pausing after the current request. Completed downloads are saved.",0,0,null,null));
    }
    @Override public void onCreate(){
        super.onCreate();
        NotificationChannel channel=new NotificationChannel(CHANNEL,"Training data sync",NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("Progress and pause control for training downloads");
        getSystemService(NotificationManager.class).createNotificationChannel(channel);
    }
    @Override public int onStartCommand(Intent intent,int flags,int startId){
        if(intent!=null&&PAUSE.equals(intent.getAction())){
            pause(this);if(owned==null)stopSelf();return START_NOT_STICKY;
        }
        if(active==null){stopSelf();return START_NOT_STICKY;}
        if(owned!=null)return START_NOT_STICKY;
        owned=active;
        Notification notification=notification("Starting sync…",0,0);
        try{
            if(Build.VERSION.SDK_INT>=29)startForeground(NOTIFICATION,notification,ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
            else startForeground(NOTIFICATION,notification);
            wakeLock=((PowerManager)getSystemService(POWER_SERVICE)).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,getPackageName()+":sync");
            wakeLock.acquire(6*60*60*1000L);
        }catch(RuntimeException error){
            owned.lifecycle.interrupt();
            finish(owned,null,"Couldn't start background sync. Reopen the app to resume.");
            return START_NOT_STICKY;
        }
        // Stop before Android 15's cumulative six-hour data-sync limit.
        MAIN.postDelayed(deadline,5*60*60*1000L+45*60*1000L);
        Run run=owned;
        BackendRuntime.WORKER.execute(()->{
            JSONObject result=null;String error=null;
            try{
                JSONObject state=BackendRuntime.initialize(getApplicationContext());
                if(!state.optBoolean("authenticated"))throw new IllegalStateException("Sign in required");
                if(!run.cancelled){
                    Object[] args="dashboard".equals(run.operation)
                        ?new Object[]{run.today,run.days,run.settings,true,new DownloadProgress(run)}
                        :new Object[]{run.today,run.days,run.settings,new DownloadProgress(run)};
                    result=BackendRuntime.invoke(getApplicationContext(),run.operation,args);
                }
            }catch(Throwable failure){error="Sync interrupted. Completed downloads are saved; reopen the app to resume.";}
            final JSONObject data=result;final String failure=error;
            MAIN.post(()->finish(run,data,failure));
        });
        return START_NOT_STICKY;
    }
    public interface ProgressSink {void update(String label,int completed,int total);boolean isCancelled();}
    public final class DownloadProgress implements ProgressSink {
        private final Run run;
        DownloadProgress(Run run){this.run=run;}
        public boolean isCancelled(){return run.cancelled;}
        public void update(String label,int completed,int total){
            MAIN.post(()->{
                if(active!=run||run.cancelled)return;
                publish(new Snapshot(run,true,label,completed,total,null,null));
                long now=android.os.SystemClock.elapsedRealtime();
                if(now-lastNotification>=1000){
                    lastNotification=now;getSystemService(NotificationManager.class).notify(NOTIFICATION,notification(label,completed,total));
                }
            });
        }
    }
    private Notification notification(String label,int completed,int total){
        PendingIntent open=PendingIntent.getActivity(this,0,new Intent(this,MainActivity.class)
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        PendingIntent pause=PendingIntent.getService(this,1,new Intent(this,SyncService.class).setAction(PAUSE),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        Notification publicView=new Notification.Builder(this,CHANNEL).setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("Run Dashboard").setContentText("Syncing training data").build();
        return new Notification.Builder(this,CHANNEL).setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("Syncing training data").setContentText(label).setContentIntent(open)
            .setOngoing(true).setOnlyAlertOnce(true).setCategory(Notification.CATEGORY_PROGRESS)
            .setVisibility(Notification.VISIBILITY_PRIVATE).setPublicVersion(publicView)
            .setProgress(Math.max(0,total),Math.max(0,completed),total<=0)
            .addAction(new Notification.Action.Builder(android.R.drawable.ic_media_pause,"Pause",pause).build()).build();
    }
    private void finish(Run run,JSONObject data,String failure){
        if(active!=run)return;
        boolean ok=data!=null&&data.optBoolean("ok");
        run.lifecycle.finish(ok,ok&&data.optBoolean("sync_paused"),System.currentTimeMillis());save(this,run);
        if(ok&&!data.optBoolean("sync_paused")&&!run.cancelled){
            getSharedPreferences("training",0).edit().putString("last_sync",LocalDateTime.now()
                .format(DateTimeFormatter.ofPattern("MMM d, HH:mm",Locale.getDefault()))).apply();
        }
        String error=failure!=null?failure:!ok&&!run.lifecycle.userPaused?(data==null?"Sync interrupted. Reopen the app to resume.":data.optString("error")):null;
        String label=run.lifecycle.userPaused?"Paused · completed downloads saved":run.lifecycle.pending?"Sync interrupted · completed downloads saved":"Sync complete";
        active=null;
        owned=null;
        release();stopForeground(STOP_FOREGROUND_REMOVE);stopSelf();
        publish(new Snapshot(run,false,label,0,0,data,error));
    }
    private void interrupt(){
        if(owned!=null&&active==owned){owned.lifecycle.interrupt();save(this,owned);owned.cancelled=true;}
        release();stopForeground(STOP_FOREGROUND_REMOVE);stopSelf();
    }
    private void release(){MAIN.removeCallbacks(deadline);if(wakeLock!=null&&wakeLock.isHeld())wakeLock.release();}
    @Override public void onTimeout(int startId,int foregroundServiceType){interrupt();}
    @Override public void onDestroy(){
        if(owned!=null&&active==owned){owned.lifecycle.interrupt();save(this,owned);owned.cancelled=true;}
        release();super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent){return null;}
}
