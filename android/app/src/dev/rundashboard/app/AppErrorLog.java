package dev.rundashboard.app;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;

/** Bounded, app-private diagnostics. Exception messages and user data are excluded. */
final class AppErrorLog {
    private static final int LIMIT=16000;
    private static File file;
    private static String version="unknown";
    private static boolean installed;
    private static byte[] reserve;
    private static String events="";
    static synchronized void install(File directory,String appVersion){
        file=new File(directory,"app-errors.txt");version=appVersion;
        if(installed)return;installed=true;reserve=new byte[65536];
        Thread.UncaughtExceptionHandler previous=Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((thread,error)->{
            reserve=null;record("uncaught",error);
            if(previous!=null)previous.uncaughtException(thread,error);else Runtime.getRuntime().halt(10);
        });
    }
    static synchronized void event(String name){
        if(name==null||!name.matches("[A-Za-z0-9_. -]{1,80}"))return;
        events+=System.currentTimeMillis()+" "+name+"\n";
        if(events.length()>1800)events=events.substring(events.length()-1800);
    }
    static String frames(Throwable error){
        StringBuilder text=new StringBuilder();
        for(int cause=0;error!=null&&cause<4;cause++,error=error.getCause()){
            text.append(cause==0?"Exception: ":"Caused by: ").append(error.getClass().getName()).append('\n');
            StackTraceElement[] stack=error.getStackTrace();
            for(int i=0;i<Math.min(36,stack.length);i++){
                StackTraceElement frame=stack[i];
                text.append("  at ").append(frame.getClassName()).append('.').append(frame.getMethodName()).append(':').append(frame.getLineNumber()).append('\n');
            }
            if(text.length()>12000)break;
        }
        return text.substring(0,Math.min(text.length(),12000));
    }
    static synchronized void record(String operation,Throwable error){
        if(file==null||error==null)return;
        if(operation==null||!operation.matches("[A-Za-z0-9_. -]{1,80}"))operation="error";
        try{
            String entry="\nApp "+version+" · epoch ms "+System.currentTimeMillis()+" · "+operation+"\n"+events+frames(error);
            String history=readFile();String combined=history+entry;
            if(combined.length()>LIMIT)combined=combined.substring(combined.length()-LIMIT);
            try(FileOutputStream output=new FileOutputStream(file)){output.write(combined.getBytes(StandardCharsets.UTF_8));}
        }catch(Throwable ignored){} // The platform's original crash handler must still run.
    }
    private static String readFile(){
        if(file==null||!file.isFile())return "";
        try(FileInputStream input=new FileInputStream(file)){
            byte[] buffer=new byte[LIMIT*3];int used=0,count;
            while(used<buffer.length&&(count=input.read(buffer,used,buffer.length-used))>0)used+=count;
            return new String(buffer,0,used,StandardCharsets.UTF_8);
        }catch(Exception ignored){return "";}
    }
    static synchronized String report(){
        String saved=readFile();
        return "Run Dashboard "+version+"\n"+(saved.isEmpty()?"No captured Java error yet.\n":saved)+"\nCurrent events:\n"+events;
    }
}
