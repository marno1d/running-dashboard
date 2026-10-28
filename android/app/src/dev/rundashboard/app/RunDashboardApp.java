package dev.rundashboard.app;

public final class RunDashboardApp extends android.app.Application {
    @Override public void onCreate(){
        super.onCreate();String version="unknown";
        try{version=getPackageManager().getPackageInfo(getPackageName(),0).versionName;}catch(Exception ignored){}
        AppErrorLog.install(getFilesDir(),version);AppErrorLog.event("app.start");
    }
}
