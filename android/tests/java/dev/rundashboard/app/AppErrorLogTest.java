package dev.rundashboard.app;

import java.nio.file.Files;
import java.io.File;

public final class AppErrorLogTest {
    public static void main(String[] args)throws Exception{
        Thread.UncaughtExceptionHandler original=Thread.getDefaultUncaughtExceptionHandler();
        File directory=Files.createTempDirectory("app-error-test").toFile();
        try{
            AppErrorLog.install(directory,"test");AppErrorLog.event("route.apply");AppErrorLog.event("password=secret");
            RuntimeException cause=new RuntimeException("password=secret https://credentials.invalid/?token=secret");
            cause.setStackTrace(new StackTraceElement[]{new StackTraceElement("dev.rundashboard.app.MainActivity","renderTargetPaces","MainActivity.java",1680)});
            AppErrorLog.record("targets.refresh",new IllegalStateException("private location",cause));
            String report=AppErrorLog.report();
            if(!report.contains("renderTargetPaces:1680")||!report.contains("java.lang.IllegalStateException")||!report.contains("route.apply"))throw new AssertionError("Missing technical context");
            for(String secret:new String[]{"password","secret","https://","private location"})if(report.contains(secret))throw new AssertionError("Sensitive exception message recorded");
            for(int i=0;i<200;i++)AppErrorLog.record("targets.refresh",cause);
            if(new File(directory,"app-errors.txt").length()>48000||AppErrorLog.report().length()>18500)throw new AssertionError("Unbounded report");
            System.out.println("Private bounded diagnostics preserve technical frames and exclude exception messages: OK");
        }finally{
            Thread.setDefaultUncaughtExceptionHandler(original);new File(directory,"app-errors.txt").delete();directory.delete();
        }
    }
}
