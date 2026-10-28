package dev.rundashboard.app;

import android.content.Context;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Build;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.Future;
import java.util.function.Consumer;
import org.json.JSONObject;

/** A bounded, cancellable foreground lookup. Coordinates are not stored or logged. */
final class LocalWeather {
    interface Listener {void complete(WeatherData data,String error);}
    private final LocationManager manager;
    private final Handler main=new Handler(Looper.getMainLooper());
    // A cancelled DNS/socket operation can take time to unwind. One retry may
    // proceed independently, without an unbounded queue of abandoned lookups.
    private final ThreadPoolExecutor network=new ThreadPoolExecutor(0,2,30,TimeUnit.SECONDS,new SynchronousQueue<>());
    private final WeatherLocation locator=new WeatherLocation();
    private Fetch fetch;
    private Runnable timeout;
    private Listener listener;
    private Runnable stageChanged;
    private int generation;
    private boolean running,locationFailure;
    private String status="Finding phone location…";
    LocalWeather(Context context){manager=(LocationManager)context.getApplicationContext().getSystemService(Context.LOCATION_SERVICE);}
    boolean running(){return running;}
    boolean needsLocationSettings(){return locationFailure;}
    String status(){return status;}
    void request(Listener listener,Runnable stageChanged){
        cancel();this.listener=listener;this.stageChanged=stageChanged;running=true;locationFailure=false;final int request=generation;
        stage("Finding phone location…");
        locator.request(new AndroidLocation(),(delay,action)->{main.postDelayed(action,delay);return ()->main.removeCallbacks(action);},(fix,error)->{
            if(request!=generation||!running)return;
            if(fix==null){locationFailure=true;finish(request,null,error);return;}
            load(request,fix);
        });
    }
    private void stage(String value){status=value;if(stageChanged!=null)stageChanged.run();}
    private WeatherLocation.Fix fix(Location location){
        return location==null?null:new WeatherLocation.Fix(location.getLatitude(),location.getLongitude(),
            (SystemClock.elapsedRealtimeNanos()-location.getElapsedRealtimeNanos())/1000000,location.getAccuracy());
    }
    private final class AndroidLocation implements WeatherLocation.Source {
        public boolean enabled(){
            if(manager==null)return false;
            if(Build.VERSION.SDK_INT>=28)return manager.isLocationEnabled();
            for(String provider:manager.getAllProviders())if(manager.isProviderEnabled(provider))return true;
            return false;
        }
        public String[] providers(){
            ArrayList<String> result=new ArrayList<>();
            for(String provider:new String[]{LocationManager.NETWORK_PROVIDER,"fused"}){
                try{if(manager.getAllProviders().contains(provider)&&manager.isProviderEnabled(provider))result.add(provider);}catch(RuntimeException ignored){}
            }
            return result.toArray(new String[0]);
        }
        public String[] cachedProviders(){return manager.getProviders(true).toArray(new String[0]);}
        public WeatherLocation.Fix lastKnown(String provider){return fix(manager.getLastKnownLocation(provider));}
        public WeatherLocation.Task current(String provider,Consumer<WeatherLocation.Fix> callback){
            if(Build.VERSION.SDK_INT>=30){
                CancellationSignal cancellation=new CancellationSignal();
                manager.getCurrentLocation(provider,cancellation,command->main.post(command),location->callback.accept(fix(location)));
                return cancellation::cancel;
            }
            LocationListener listener=new LocationListener(){
                public void onLocationChanged(Location location){callback.accept(fix(location));}
                public void onProviderDisabled(String provider){callback.accept(null);}
                public void onProviderEnabled(String provider){}
                public void onStatusChanged(String provider,int status,Bundle extras){}
            };
            manager.requestSingleUpdate(provider,listener,Looper.getMainLooper());
            return ()->manager.removeUpdates(listener);
        }
    }
    private void load(int request,WeatherLocation.Fix location){
        if(request!=generation||!running)return;
        stage("Downloading local weather…");
        // The HTTP budget starts after location succeeds, so a slower fix does
        // not consume the time available to download the forecast.
        timeout=()->finish(request,null,"Weather download timed out. Check your internet connection, then retry.");main.postDelayed(timeout,25000);
        fetch=new Fetch(request,WeatherData.url(location.latitude,location.longitude));
        try{fetch.future=network.submit(fetch);}
        catch(java.util.concurrent.RejectedExecutionException error){finish(request,null,"A previous weather connection is still closing. Try again shortly.");}
    }
    private final class Fetch implements Runnable {
        final int request;final String address;volatile HttpURLConnection connection;volatile boolean cancelled;Future<?> future;
        Fetch(int request,String address){this.request=request;this.address=address;}
        void cancel(){cancelled=true;if(future!=null)future.cancel(true);HttpURLConnection current=connection;if(current!=null)current.disconnect();}
        @Override public void run(){
            HttpURLConnection http=null;
            try{
                if(cancelled)return;
                http=(HttpURLConnection)new URL(address).openConnection();connection=http;
                if(cancelled)return;
                http.setConnectTimeout(8000);http.setReadTimeout(10000);http.setInstanceFollowRedirects(false);http.setUseCaches(false);
                http.setRequestProperty("Accept","application/json");http.setRequestProperty("User-Agent","RunDashboard");
                if(http.getResponseCode()!=200)throw new java.io.IOException();
                ByteArrayOutputStream bytes=new ByteArrayOutputStream();
                try(InputStream input=http.getInputStream()){
                    byte[] buffer=new byte[2048];int count;
                    while((count=input.read(buffer))!=-1){if(cancelled)return;if(bytes.size()+count>65536)throw new java.io.IOException();bytes.write(buffer,0,count);}
                }
                JSONObject response=new JSONObject(new String(bytes.toByteArray(),StandardCharsets.UTF_8));
                JSONObject units=response.getJSONObject("current_units"),current=response.getJSONObject("current");
                if(!"°F".equals(units.optString("temperature_2m"))||!"%".equals(units.optString("relative_humidity_2m")))throw new IllegalArgumentException("Unexpected weather units. Try again.");
                WeatherData data=new WeatherData(current.optDouble("temperature_2m",Double.NaN),current.optDouble("relative_humidity_2m",Double.NaN),current.getLong("time")*1000,System.currentTimeMillis());
                main.post(()->finish(request,data,null));
            }catch(Exception error){
                String reason=error instanceof IllegalArgumentException?error.getMessage():"Couldn't download local weather. Check your connection or edit the fields.";
                main.post(()->finish(request,null,reason));
            }finally{if(http!=null)http.disconnect();connection=null;}
        }
    }
    private void finish(int request,WeatherData data,String error){
        if(request!=generation||!running)return;Listener callback=listener;cancel();if(callback!=null)callback.complete(data,error);
    }
    void cancel(){
        generation++;running=false;listener=null;stageChanged=null;locator.cancel();
        if(timeout!=null){main.removeCallbacks(timeout);timeout=null;}
        if(fetch!=null){fetch.cancel();fetch=null;}
    }
    void close(){cancel();network.shutdownNow();}
}
