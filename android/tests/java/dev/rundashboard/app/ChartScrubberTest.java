package dev.rundashboard.app;

public final class ChartScrubberTest {
    private static void expect(int actual,int expected){if(actual!=expected)throw new AssertionError(actual+" != "+expected);}
    private static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    private static int pick(ChartSeries series,double day){
        // Mixed order, an invalid sample, and an unrelated series closer than the active series.
        return ChartScrubber.nearest(new double[]{20,10,15,12,Double.NaN,13},new double[]{310,300,320,330,340,Double.NaN},
            new String[]{"short","short","medium","long","short","short"},series.firstVisible(),day,0,25,0,400);
    }
    public static void main(String[] args){
        ChartSeries series=new ChartSeries(ChartSeries.INTERVAL);
        expect(pick(series,14),1); // Short, despite closer Medium / Long samples.
        expect(pick(series,15),1); // Equal date distance prefers earlier, even when unsorted.
        expect(pick(series,15.01),0);
        series.setVisible("short",false);expect(pick(series,14),2);
        series.setVisible("medium",false);expect(pick(series,14),3);
        series.setVisible("long",false);expect(pick(series,14),-1);
        series.setVisible("short",true);expect(pick(series,14),1);
        // An enabled series with no visible measurements does not borrow another series' values.
        expect(ChartScrubber.nearest(new double[]{10},new double[]{100},new String[]{"medium"},"short",10,0,20,0,200),-1);
        // Window limits matter after zoom and for fixed pace scales.
        expect(ChartScrubber.nearest(new double[]{10,20,30},new double[]{300,400,500},new String[]{"x","x","x"},"x",10,15,25,0,600),1);
        expect(ChartScrubber.nearest(new double[]{10,20,30},new double[]{300,400,500},new String[]{"x","x","x"},"x",20,0,40,450,550),2);
        expect(ChartScrubber.nearest(new double[]{10},new double[]{300},new String[]{"x"},"x",10,20,30,0,500),-1);
        // Zero is a real HR-compliance or load value; empty and missing data stay empty.
        expect(ChartScrubber.nearest(new double[]{10},new double[]{0},new String[]{"low"},"low",10,0,20,0,100),0);
        expect(ChartScrubber.nearest(new double[0],new double[0],new String[0],"",10,0,20,0,100),-1);
        expect(ChartScrubber.nearest(new double[]{10},new double[]{Double.NaN},new String[]{"x"},"x",10,0,20,0,100),-1);
        expect(ChartScrubber.nearest(new double[]{10},new double[]{100},new String[]{"x"},"x",Double.NaN,0,20,0,200),-1);
        // No legend (weekly load) accepts its sole series; recovery targets a specific lane.
        expect(ChartScrubber.nearest(new double[]{10,17},new double[]{3,4},new String[]{"load","load"},"",16,0,20,0,10),1);
        expect(ChartScrubber.nearest(new double[]{10,10,17},new double[]{7,55,8},new String[]{"sleep","hr","sleep"},"sleep",11,0,20,0,100),0);
        // Repetitions on the same day follow finger height without switching legend series.
        expect(ChartScrubber.nearest(new double[]{10,10,10},new double[]{300,330,325},new String[]{"short","short","medium"},"short",10,0,20,0,400,326),1);
        // The guide follows fractional dates smoothly and clamps at plot edges.
        check(ChartScrubber.day(125,100,200,10,20)==12.5,"fractional cursor date");
        check(ChartScrubber.day(126,100,200,10,20)>12.5,"cursor follows small finger movements");
        check(ChartScrubber.day(0,100,200,10,20)==10,"left clamp");
        check(ChartScrubber.day(300,100,200,10,20)==20,"right clamp");
        check(Double.isNaN(ChartScrubber.day(100,100,100,10,20)),"unlaid-out plot");
        // Legend order, not activation order, controls scrubbing.
        check("short".equals(series.firstVisible()),"first restored item");
        series.setVisible("long",true);check("short".equals(series.firstVisible()),"legend order is stable");
        check(new ChartSeries(ChartSeries.NONE).firstVisible().isEmpty(),"no-legend chart");
        System.out.println("Chart scrubbing: legend priority, real values, zoom bounds, missing data, duplicate-date reps and smooth cursor geometry: OK");
    }
}
