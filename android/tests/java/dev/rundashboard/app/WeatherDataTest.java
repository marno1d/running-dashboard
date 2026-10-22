package dev.rundashboard.app;

import java.net.URI;
import java.util.Locale;

public final class WeatherDataTest {
    private static void check(boolean value){if(!value)throw new AssertionError();}
    private static void rejected(Runnable action){try{action.run();throw new AssertionError("Expected rejection");}catch(IllegalArgumentException expected){}}
    public static void main(String[] args)throws Exception{
        long now=1700000000000L;
        WeatherData data=new WeatherData(45.6,52.3,now-900000,now);
        check("46".equals(data.temperatureText()));check("52".equals(data.humidityText()));
        check("-10".equals(new WeatherData(-10.2,0,now,now).temperatureText()));
        check("100".equals(new WeatherData(90,100,now,now).humidityText()));
        for(double invalid:new double[]{Double.NaN,Double.POSITIVE_INFINITY,-151,161})rejected(()->new WeatherData(invalid,50,now,now));
        for(double invalid:new double[]{Double.NaN,-1,101})rejected(()->new WeatherData(50,invalid,now,now));
        rejected(()->new WeatherData(50,50,0,now));
        rejected(()->new WeatherData(50,50,now-2*WeatherPolicy.HOUR-1,now));
        rejected(()->new WeatherData(50,50,now+15*60*1000+1,now));
        check(WeatherData.freshLocation(0,2000));check(WeatherData.freshLocation(300000,20000));
        check(!WeatherData.freshLocation(300001,2000));check(!WeatherData.freshLocation(-1,2000));
        check(!WeatherData.freshLocation(0,0));check(!WeatherData.freshLocation(0,20001));check(!WeatherData.freshLocation(0,Float.NaN));
        Locale previous=Locale.getDefault();
        try{
            Locale.setDefault(Locale.GERMANY);
            String url=WeatherData.url(52.523456,13.412345);
            URI parsed=new URI(url);check("https".equals(parsed.getScheme()));check("api.open-meteo.com".equals(parsed.getHost()));
            check(url.contains("latitude=52.52&longitude=13.41&"));
            check(!url.contains("523456")&&!url.contains("412345"));
            check(url.contains("current=temperature_2m,relative_humidity_2m"));check(url.contains("temperature_unit=fahrenheit"));check(url.contains("timeformat=unixtime"));
            // The complete query is a fixed allowlist: no account, device ID, activity or route fields.
            check(parsed.getRawQuery().split("&").length==6);
            check(WeatherData.url(-40.126,-111.895).contains("latitude=-40.13&longitude=-111.90"));
            rejected(()->WeatherData.url(Double.NaN,0));rejected(()->WeatherData.url(91,0));rejected(()->WeatherData.url(0,181));
        }finally{Locale.setDefault(previous);}
        System.out.println("Local weather: rounded coordinates, fixed HTTPS query, units, missing/stale data and location freshness: OK");
    }
}
