package dev.rundashboard.app;

import java.util.*;
import java.util.function.Consumer;

/** Real lookup coordinator with fake providers and clock: no phone location is read. */
public final class WeatherLocationTest {
    private static void check(boolean value){if(!value)throw new AssertionError();}
    private static WeatherLocation.Fix fix(long age){return new WeatherLocation.Fix(40.123456,-111.987654,age,2000);}
    private static final class Timer implements WeatherLocation.Scheduler {
        final List<Entry> entries=new ArrayList<>();long now;
        final class Entry implements WeatherLocation.Task {long at;Runnable action;boolean cancelled;public void cancel(){cancelled=true;}}
        public WeatherLocation.Task after(long delay,Runnable action){Entry entry=new Entry();entry.at=now+delay;entry.action=action;entries.add(entry);return entry;}
        void advance(long milliseconds){
            long target=now+milliseconds;
            while(true){Entry next=null;for(Entry entry:entries)if(!entry.cancelled&&entry.at<=target&&(next==null||entry.at<next.at))next=entry;
                if(next==null)break;now=next.at;next.cancelled=true;next.action.run();}
            now=target;
        }
    }
    private static class Providers implements WeatherLocation.Source {
        boolean enabled=true;
        String[] available={"network","fused"},cached={"network","fused","passive","gps"};
        final Map<String,WeatherLocation.Fix> fixes=new HashMap<>();
        final Map<String,Consumer<WeatherLocation.Fix>> callbacks=new HashMap<>();
        final Set<String> cancelled=new HashSet<>(),denied=new HashSet<>();
        public boolean enabled(){return enabled;}
        public String[] providers(){return available;}
        public String[] cachedProviders(){return cached;}
        public WeatherLocation.Fix lastKnown(String provider){if(denied.contains(provider))throw new SecurityException();return fixes.get(provider);}
        public WeatherLocation.Task current(String provider,Consumer<WeatherLocation.Fix> callback){
            if(denied.contains(provider))throw new SecurityException();callbacks.put(provider,callback);return ()->cancelled.add(provider);
        }
        void reply(String provider,WeatherLocation.Fix location){callbacks.get(provider).accept(location);}
    }
    private static final class Answer implements WeatherLocation.Result {
        int calls;WeatherLocation.Fix location;String error;
        public void complete(WeatherLocation.Fix fix,String error){calls++;location=fix;this.error=error;}
    }
    public static void main(String[] args){
        { // A fused provider that never responds cannot block the network provider.
            WeatherLocation lookup=new WeatherLocation();Providers providers=new Providers();Timer timer=new Timer();Answer answer=new Answer();
            lookup.request(providers,timer,answer);check(providers.callbacks.size()==2);providers.reply("network",fix(0));
            check(answer.calls==1&&answer.location!=null&&answer.error==null);check(providers.cancelled.size()==2);
            providers.reply("fused",fix(0));timer.advance(30000);check(answer.calls==1);
        }
        { // A null response is a failure of that provider, not of the whole lookup.
            WeatherLocation lookup=new WeatherLocation();Providers providers=new Providers();Timer timer=new Timer();Answer answer=new Answer();
            lookup.request(providers,timer,answer);providers.reply("network",null);check(answer.calls==0);
            providers.reply("fused",fix(0));check(answer.calls==1&&answer.location!=null);
        }
        { // An inaccessible provider does not stop another coarse provider.
            WeatherLocation lookup=new WeatherLocation();Providers providers=new Providers();Timer timer=new Timer();Answer answer=new Answer();
            providers.denied.add("network");lookup.request(providers,timer,answer);providers.reply("fused",fix(0));
            check(answer.calls==1&&answer.location!=null);
        }
        { // Inspect all accessible caches, taking the newest usable fix.
            WeatherLocation lookup=new WeatherLocation();Providers providers=new Providers();Timer timer=new Timer();Answer answer=new Answer();
            providers.fixes.put("network",fix(600000));providers.fixes.put("passive",fix(120000));providers.denied.add("gps");
            lookup.request(providers,timer,answer);check(answer.calls==1&&answer.location.ageMillis==120000);check(providers.callbacks.isEmpty());
        }
        { // Approximate location may be older than the previous five-minute cutoff.
            WeatherLocation lookup=new WeatherLocation();Providers providers=new Providers();Timer timer=new Timer();Answer answer=new Answer();
            providers.fixes.put("network",fix(600000));lookup.request(providers,timer,answer);
            check(answer.calls==1&&answer.location!=null&&providers.callbacks.isEmpty());
        }
        { // Do not fetch weather for a stale or very inaccurate area.
            WeatherLocation lookup=new WeatherLocation();Providers providers=new Providers();Timer timer=new Timer();Answer answer=new Answer();
            providers.fixes.put("network",fix(900001));providers.fixes.put("fused",new WeatherLocation.Fix(40,-111,0,30000));
            lookup.request(providers,timer,answer);check(answer.calls==0&&providers.callbacks.size()==2);
            providers.reply("network",fix(0));check(answer.calls==1&&answer.location!=null);
        }
        { // Location switched off wins over any old cache.
            WeatherLocation lookup=new WeatherLocation();Providers providers=new Providers();Timer timer=new Timer();Answer answer=new Answer();
            providers.enabled=false;providers.fixes.put("network",fix(0));lookup.request(providers,timer,answer);
            check(answer.calls==1&&answer.location==null&&answer.error.contains("off"));check(providers.callbacks.isEmpty());
        }
        { // A missing provider fails promptly, rather than waiting for a global timeout.
            WeatherLocation lookup=new WeatherLocation();Providers providers=new Providers();Timer timer=new Timer();Answer answer=new Answer();
            providers.available=new String[0];lookup.request(providers,timer,answer);
            check(answer.calls==1&&answer.error!=null&&timer.entries.isEmpty());
        }
        { // Silent providers time out and both requests are cancelled.
            WeatherLocation lookup=new WeatherLocation();Providers providers=new Providers();Timer timer=new Timer();Answer answer=new Answer();
            lookup.request(providers,timer,answer);timer.advance(19999);check(answer.calls==0);timer.advance(1);
            check(answer.calls==1&&answer.location==null&&answer.error.contains("location timed out"));check(providers.cancelled.size()==2);
            providers.reply("network",fix(0));check(answer.calls==1);
        }
        { // An old provider callback after cancellation cannot replace a newer request.
            WeatherLocation lookup=new WeatherLocation();Providers old=new Providers(),current=new Providers();Timer timer=new Timer();Answer first=new Answer(),second=new Answer();
            lookup.request(old,timer,first);lookup.cancel();lookup.request(current,timer,second);old.reply("network",fix(0));
            check(first.calls==0&&second.calls==0);current.reply("fused",fix(0));check(second.calls==1);
        }
        { // A synchronous provider response still cancels the task it returns.
            WeatherLocation lookup=new WeatherLocation();Timer timer=new Timer();Answer answer=new Answer();
            Providers providers=new Providers(){@Override public WeatherLocation.Task current(String provider,Consumer<WeatherLocation.Fix> callback){callback.accept(fix(0));return ()->cancelled.add(provider);}};
            lookup.request(providers,timer,answer);check(answer.calls==1&&providers.cancelled.contains("network"));
        }
        { // A slow location fix does not consume the following HTTP-stage deadline.
            WeatherLocation lookup=new WeatherLocation();Providers providers=new Providers();Timer timer=new Timer();final int[] downloads={0},timeouts={0};
            lookup.request(providers,timer,(location,error)->{check(location!=null);downloads[0]++;timer.after(25000,()->timeouts[0]++);});
            timer.advance(19000);providers.reply("network",fix(0));timer.advance(1000);
            check(downloads[0]==1&&timeouts[0]==0);timer.advance(23999);check(timeouts[0]==0);timer.advance(1);check(timeouts[0]==1);
        }
        System.out.println("Weather location: silent/null provider fallback, recent caches, bounded stages, cancellation and late callbacks: OK");
    }
}
