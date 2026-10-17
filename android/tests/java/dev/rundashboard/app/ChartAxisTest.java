package dev.rundashboard.app;

public final class ChartAxisTest {
    public static void main(String[] args){
        for(double[] range:new double[][]{{240,360},{252.5,289.5},{900,1800},{0,100},{12.3,13.1},{0,3},{-1,1}}){
            for(boolean time:new boolean[]{false,true}){
                double[] ticks=ChartAxis.ticks(range[0],range[1],4,time);
                if(ticks.length==0||ticks.length>6)throw new AssertionError("unreadable tick density");
                for(int i=0;i<ticks.length;i++){
                    if(ticks[i]<range[0]-1e-8||ticks[i]>range[1]+1e-8)throw new AssertionError("tick outside zoomed domain");
                    if(i>0&&ticks[i]<=ticks[i-1])throw new AssertionError("unordered labels");
                }
            }
        }
        double[] pace=ChartAxis.ticks(240,360,4,true);
        if(pace.length!=5||pace[1]!=270)throw new AssertionError("pace labels should use 30-second steps");
        if(ChartAxis.ticks(1,1,4,false).length!=0)throw new AssertionError("invalid range");
        double[] counts=ChartAxis.ticks(0,1,4,false,1);
        if(counts.length!=2||counts[1]!=1)throw new AssertionError("small integer domains must not repeat rounded labels");
        for(int available:new int[]{96,160,240,360})for(int label:new int[]{40,60,100}){
            long[] dates=ChartAxis.dates(100-.5,190+.5,available,label,24);
            if(dates.length>1&&dates.length*label+(dates.length-1)*24>available)throw new AssertionError("date labels overlap");
            for(int i=1;i<dates.length;i++)if(dates[i]<=dates[i-1])throw new AssertionError("duplicate dates");
        }
        if(ChartAxis.dates(100.1,100.3,240,40,24).length!=1)throw new AssertionError("sub-day zoom needs a single date");
        if(ChartAxis.dates(100,101,600,40,24).length!=2)throw new AssertionError("two visible dates must not repeat");
        System.out.println("Pace and numeric axis labels remain ordered, readable and within the visible range: OK");
    }
}
