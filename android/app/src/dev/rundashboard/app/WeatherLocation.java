package dev.rundashboard.app;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.function.Consumer;

/** One bounded foreground lookup, independent of Android so provider failures can be tested. */
final class WeatherLocation {
    interface Task {void cancel();}
    interface Scheduler {Task after(long milliseconds,Runnable action);}
    interface Source {
        boolean enabled();
        String[] providers();
        default String[] cachedProviders(){return providers();}
        Fix lastKnown(String provider);
        Task current(String provider,Consumer<Fix> callback);
    }
    interface Result {void complete(Fix fix,String error);}
    static final class Fix {
        final double latitude,longitude;final long ageMillis;final float accuracy;
        Fix(double latitude,double longitude,long ageMillis,float accuracy){this.latitude=latitude;this.longitude=longitude;this.ageMillis=ageMillis;this.accuracy=accuracy;}
        boolean usable(){return Double.isFinite(latitude)&&Double.isFinite(longitude)&&Math.abs(latitude)<=90&&Math.abs(longitude)<=180&&WeatherData.freshLocation(ageMillis,accuracy);}
    }
    static final String UNAVAILABLE="Couldn't get a phone location. Check Location and location accuracy in phone settings, then retry.";
    private final List<Task> requests=new ArrayList<>();
    private final Set<String> pending=new LinkedHashSet<>();
    private Task deadline;private Result result;private int generation;private boolean active;
    void request(Source source,Scheduler scheduler,Result result){
        cancel();this.result=result;active=true;final int request=generation;
        try{
            if(!source.enabled()){finish(request,null,"Phone location is off. Turn on Location in phone settings, then retry.");return;}
            Fix best=null;
            for(String provider:source.cachedProviders()){
                try{Fix fix=source.lastKnown(provider);if(fix!=null&&fix.usable()&&(best==null||fix.ageMillis<best.ageMillis||fix.ageMillis==best.ageMillis&&fix.accuracy<best.accuracy))best=fix;}
                catch(RuntimeException ignored){} // A cache/provider may be inaccessible with coarse permission.
            }
            if(best!=null){finish(request,best,null);return;}
            for(String provider:source.providers())pending.add(provider);
            if(pending.isEmpty()){finish(request,null,UNAVAILABLE);return;}
            deadline=scheduler.after(20000,()->finish(request,null,"Phone location timed out. Check Location and location accuracy in phone settings, then retry."));
            // Start every available coarse provider. A silent/null provider must
            // not prevent another one from delivering an approximate location.
            for(String provider:new ArrayList<>(pending)){
                if(!active||request!=generation)break;
                try{
                    Task task=source.current(provider,fix->{
                        if(!active||request!=generation)return;
                        if(fix!=null&&fix.usable()){finish(request,fix,null);return;}
                        pending.remove(provider);if(pending.isEmpty())finish(request,null,UNAVAILABLE);
                    });
                    if(!active||request!=generation){if(task!=null)task.cancel();}
                    else if(task!=null)requests.add(task);
                }catch(RuntimeException ignored){pending.remove(provider);if(pending.isEmpty())finish(request,null,UNAVAILABLE);}
            }
        }catch(SecurityException error){finish(request,null,"Allow approximate location for Run Dashboard in app settings, then retry.");}
        catch(RuntimeException error){finish(request,null,UNAVAILABLE);}
    }
    private void finish(int request,Fix fix,String error){
        if(!active||request!=generation)return;Result callback=result;cancel();if(callback!=null)callback.complete(fix,error);
    }
    void cancel(){
        generation++;active=false;result=null;
        if(deadline!=null){deadline.cancel();deadline=null;}
        List<Task> previous=new ArrayList<>(requests);requests.clear();pending.clear();
        for(Task task:previous)try{task.cancel();}catch(RuntimeException ignored){}
    }
}
