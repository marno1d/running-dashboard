package dev.rundashboard.app;

public final class TargetConditionsTest {
    private static void check(boolean value){if(!value)throw new AssertionError();}
    public static void main(String[] args){
        check(TargetConditions.valid(0,"-15.5"));check(TargetConditions.valid(0," 45 "));
        for(int field=0;field<4;field++){
            check(TargetConditions.valid(field,""));check(TargetConditions.valid(field,"0"));
            for(String invalid:new String[]{"-",".","NaN","Infinity","1e999","rain"})check(!TargetConditions.valid(field,invalid));
        }
        check(TargetConditions.valid(1,"100"));check(TargetConditions.valid(1,"0"));
        check(!TargetConditions.valid(1,"-1"));check(!TargetConditions.valid(1,"101"));
        for(int field=2;field<4;field++){check(TargetConditions.valid(field,"150.5"));check(!TargetConditions.valid(field,"-1"));}
        long now=1700000000000L,until=now+WeatherPolicy.HOUR;
        check(WeatherPolicy.held(now,until));check(WeatherPolicy.held(until-1,until));check(!WeatherPolicy.held(until,until));
        check(!WeatherPolicy.shouldRefresh(now,until,0,0)); // Reopening the app cannot replace a manual edit.
        check(WeatherPolicy.shouldRefresh(until,until,now,now));
        check(WeatherPolicy.shouldRefresh(now,0,0,0));
        check(!WeatherPolicy.shouldRefresh(now,0,now-1000,0));
        check(!WeatherPolicy.shouldRefresh(now,0,0,now-1000));
        check(!WeatherPolicy.shouldRefresh(now,0,0,now-2*60*1000)); // No frequent automatic retries after failure.
        check(!WeatherPolicy.shouldRefresh(now,0,0,now-WeatherPolicy.REFRESH+1));
        check(WeatherPolicy.shouldRefresh(now,0,0,now-WeatherPolicy.REFRESH));
        check(WeatherPolicy.shouldRefresh(now,0,now-WeatherPolicy.REFRESH,now-WeatherPolicy.REFRESH));
        check(!WeatherPolicy.shouldRefresh(now,0,now+1000,now+1000)); // No extra requests after a clock rollback.
        check(!WeatherPolicy.shouldRefresh(now,0,now,now)); // An explicit manual request resets the automatic cooldown.
        check(WeatherPolicy.held(until,until+WeatherPolicy.HOUR)); // A later edit restarts the hour.
        check(WeatherPolicy.shouldRequest(true,now,until,now,now)); // Explicit refresh bypasses both limits.
        check(!WeatherPolicy.shouldRequest(false,now,until,now,now));
        check(!WeatherPolicy.shouldRequest(false,now+WeatherPolicy.REFRESH-1,0,now,now));
        check(WeatherPolicy.shouldRequest(false,now+WeatherPolicy.REFRESH,0,now,now));
        System.out.println("Inline conditions: partial edits, humidity/elevation bounds, saved manual hold, expiry and refresh throttling: OK");
    }
}
