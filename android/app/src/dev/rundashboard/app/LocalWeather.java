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
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.json.JSONObject;

/** A bounded, cancellable foreground lookup. Coordinates are not stored or logged. */
final class LocalWeather {
    interface Listener {void complete(WeatherData data,String error);}
    private final LocationManager manager;
    private final Handler main=new Handler(Looper.getMainLooper());
    private final ExecutorService network=Executors.newSingleThreadExecutor();
    private CancellationSignal cancellation;
    private LocationListener locationListener;
    private Future<?> task;
    private volatile HttpURLConnection connection;
    private Runnable timeout;
    private Listener listener;
    private int generation;
    private boolean running,fetching;
    LocalWeather(Context context){manager=(LocationManager)context.getApplicationContext().getSystemService(Context.LOCATION_SERVICE);}
    boolean running(){return running;}
    void request(Listener listener){
        cancel();this.listener=listener;running=true;final int request=generation;
        timeout=()->finish(request,null,"Couldn't get local weather in time. Edit the fields or try again.");main.postDelayed(timeout,30000);
        try{
            if(manager==null)throw new IllegalStateException();
            String provider=null;
            for(String candidate:new String[]{"fused",LocationManager.NETWORK_PROVIDER}){
                if(manager.getAllProviders().contains(candidate)&&manager.isProviderEnabled(candidate)){provider=candidate;break;}
            }
            if(provider==null){finish(request,null,"Turn on phone location to use local weather. You can also edit the fields.");return;}
            Location saved=manager.getLastKnownLocation(provider);
            if(usable(saved)){load(request,saved);return;}
            if(Build.VERSION.SDK_INT>=30){
                cancellation=new CancellationSignal();
                manager.getCurrentLocation(provider,cancellation,command->main.post(command),location->{
                    if(request!=generation||fetching)return;
                    if(usable(location))load(request,location);else finish(request,null,"Couldn't get a recent location. Try again or edit the fields.");
                });
            }else{
                locationListener=new LocationListener(){
                    public void onLocationChanged(Location location){if(usable(location))load(request,location);}
                    public void onProviderDisabled(String provider){finish(request,null,"Phone location is off. Edit the fields or enable location.");}
                    public void onProviderEnabled(String provider){}
                    public void onStatusChanged(String provider,int status,Bundle extras){}
                };
                manager.requestSingleUpdate(provider,locationListener,Looper.getMainLooper());
            }
        }catch(SecurityException error){finish(request,null,"Allow approximate location to use local weather.");}
        catch(Exception error){finish(request,null,"Location unavailable. Try again or edit the fields.");}
    }
    private boolean usable(Location location){
        return location!=null&&Double.isFinite(location.getLatitude())&&Double.isFinite(location.getLongitude())&&Math.abs(location.getLatitude())<=90&&Math.abs(location.getLongitude())<=180
            &&WeatherData.freshLocation((SystemClock.elapsedRealtimeNanos()-location.getElapsedRealtimeNanos())/1000000,location.getAccuracy());
    }
    private void stopLocation(){
        if(cancellation!=null){cancellation.cancel();cancellation=null;}
        if(locationListener!=null){try{manager.removeUpdates(locationListener);}catch(Exception ignored){}locationListener=null;}
    }
    private void load(int request,Location location){
        if(request!=generation||!running||fetching)return;fetching=true;stopLocation();
        final String address=WeatherData.url(location.getLatitude(),location.getLongitude());
        task=network.submit(()->{
            HttpURLConnection http=null;
            try{
                http=(HttpURLConnection)new URL(address).openConnection();connection=http;
                http.setConnectTimeout(8000);http.setReadTimeout(10000);http.setInstanceFollowRedirects(false);http.setUseCaches(false);
                http.setRequestProperty("Accept","application/json");http.setRequestProperty("User-Agent","RunDashboard/0.19");
                if(http.getResponseCode()!=200)throw new java.io.IOException();
                ByteArrayOutputStream bytes=new ByteArrayOutputStream();
                try(InputStream input=http.getInputStream()){
                    byte[] buffer=new byte[2048];int count;
                    while((count=input.read(buffer))!=-1){if(bytes.size()+count>65536)throw new java.io.IOException();bytes.write(buffer,0,count);}
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
        });
    }
    private void finish(int request,WeatherData data,String error){
        if(request!=generation||!running)return;Listener callback=listener;cancel();if(callback!=null)callback.complete(data,error);
    }
    void cancel(){
        generation++;running=fetching=false;listener=null;stopLocation();
        if(timeout!=null){main.removeCallbacks(timeout);timeout=null;}
        if(task!=null){task.cancel(true);task=null;}HttpURLConnection http=connection;if(http!=null)http.disconnect();
    }
    void close(){cancel();network.shutdownNow();}
}
