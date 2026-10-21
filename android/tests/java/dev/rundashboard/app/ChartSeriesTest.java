package dev.rundashboard.app;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;

public final class ChartSeriesTest {
    private static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    private static void same(String actual,String expected){check(expected.equals(actual),actual+" != "+expected);}
    public static void main(String[] args){
        ChartSeries prediction=new ChartSeries(ChartSeries.PREDICTION);
        same(prediction.preferenceKey("trial"),"show_trial_points");
        same(prediction.preferenceKey("prediction"),"show_prediction_points");
        same(prediction.preferenceKey("easy_prediction"),"show_easy_prediction_points");
        prediction.setVisible("prediction",false);
        check(!prediction.pointVisible("prediction","running",95),"interval estimate line hides");
        check(prediction.pointVisible("trial","running",95),"measured efforts stay visible");
        check(prediction.pointVisible("easy_prediction","running",95),"easy estimate stays visible");

        ChartSeries interval=new ChartSeries(ChartSeries.INTERVAL);
        interval.setVisible("short",false);
        check(!interval.pointVisible("short","running",95),"short reps hide independently");
        check(interval.pointVisible("medium","running",95)&&interval.pointVisible("long","running",95),"other interval types stay visible");
        check(!interval.preferenceKey("short").equals(prediction.preferenceKey("prediction")),"charts keep independent preferences");

        ChartSeries easy=new ChartSeries(ChartSeries.EASY);
        same(easy.seriesId("easy","trail_running",0),"trail");
        same(easy.seriesId("easy_long","running",0),"road");
        same(easy.seriesId("easy","treadmill_running",0),"road");
        easy.setVisible("road",false);
        check(!easy.pointVisible("easy","running",95),"road points hide");
        check(!easy.pointVisible("easy_long","treadmill_running",95),"treadmill and Easy Long share the road legend");
        check(easy.pointVisible("easy","trail_running",95),"trail symbols stay visible");
        easy.setVisible("road",true);easy.setVisible("trail",false);
        check(easy.pointVisible("easy","running",95)&&!easy.pointVisible("easy","trail_running",95),"trail hides separately");

        ChartSeries heart=new ChartSeries(ChartSeries.HEART);
        for(double value:new double[]{0,74.999})same(heart.seriesId("easy","running",value),"low");
        for(double value:new double[]{75,89.999})same(heart.seriesId("easy","running",value),"middle");
        for(double value:new double[]{90,100})same(heart.seriesId("easy","running",value),"high");
        heart.setVisible("middle",false);
        check(!heart.pointVisible("easy","running",75)&&heart.pointVisible("easy","running",90),"HR color buckets follow the legend boundaries");
        check(heart.pointVisible("easy","running",0),"zero compliance is a real visible measurement");

        HashSet<String> preferenceKeys=new HashSet<>();
        for(String mode:new String[]{ChartSeries.PREDICTION,ChartSeries.INTERVAL,ChartSeries.EASY,ChartSeries.HEART}){
            ChartSeries series=new ChartSeries(mode);
            check(series.ids.length==series.labels.length&&series.ids.length==series.markers.length&&series.ids.length==series.colors.length,"legend metadata stays aligned");
            Map<String,Boolean> saved=new HashMap<>();
            for(String id:series.ids){
                check(series.isVisible(id),"initial visibility");
                check(preferenceKeys.add(series.preferenceKey(id)),"preference keys cannot collide between legends");
                series.setVisible(id,false);saved.put(series.preferenceKey(id),false);
            }
            check(!series.anyVisible(),"all series can be hidden without losing the legend");
            int entries=series.ids.length;
            ChartSeries reopened=new ChartSeries(mode);
            for(String id:reopened.ids)reopened.setVisible(id,saved.get(reopened.preferenceKey(id)));
            check(!reopened.anyVisible()&&reopened.ids.length==entries,"restored hidden series still have legend buttons");
            reopened.setVisible(reopened.ids[0],true);
            check(reopened.anyVisible()&&reopened.isVisible(reopened.ids[0]),"a hidden legend item can restore its series");
        }
        ChartSeries none=new ChartSeries(ChartSeries.NONE);
        check(none.ids.length==0&&none.pointVisible("anything","",Double.NaN),"charts without legends keep all their data");
        System.out.println("Chart legend visibility: independent series, trail/road and HR buckets, hide-all/restore, and preference compatibility: OK");
    }
}
