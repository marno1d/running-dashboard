package dev.rundashboard.app;

import java.util.Locale;

/** Only weather values and the model timestamp are retained after a lookup. */
final class WeatherData {
    final double temperature,humidity;
    final long time;
    WeatherData(double temperature,double humidity,long time,long now){
        if(!Double.isFinite(temperature)||temperature< -150||temperature>160||!Double.isFinite(humidity)||humidity<0||humidity>100
            ||time<=0||now-time>2*WeatherPolicy.HOUR||time-now>15*60*1000L)throw new IllegalArgumentException("Weather data is missing or out of date. Try again.");
        this.temperature=temperature;this.humidity=humidity;this.time=time;
    }
    String temperatureText(){return Long.toString(Math.round(temperature));}
    String humidityText(){return Long.toString(Math.round(humidity));}
    static String url(double latitude,double longitude){
        if(!Double.isFinite(latitude)||!Double.isFinite(longitude)||Math.abs(latitude)>90||Math.abs(longitude)>180)throw new IllegalArgumentException("Location unavailable.");
        // Send an approximate area, never the full location fix, a route, or an identifier.
        return String.format(Locale.ROOT,"https://api.open-meteo.com/v1/forecast?latitude=%.2f&longitude=%.2f&current=temperature_2m,relative_humidity_2m&temperature_unit=fahrenheit&timeformat=unixtime&forecast_days=1",latitude,longitude);
    }
    static boolean freshLocation(long ageMillis,float accuracy){return ageMillis>=0&&ageMillis<=5*60*1000L&&Float.isFinite(accuracy)&&accuracy>0&&accuracy<=20000;}
}
