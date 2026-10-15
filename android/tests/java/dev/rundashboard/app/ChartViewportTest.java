package dev.rundashboard.app;
public final class ChartViewportTest {
    static void close(double actual,double expected){if(Math.abs(actual-expected)>1e-6)throw new AssertionError(actual+" != "+expected);}
    static void check(boolean condition){if(!condition)throw new AssertionError();}
    public static void main(String[] args){
        ChartViewport chart=new ChartViewport();chart.configure(0,100,200,1000,405,600);
        close(chart.yMin,405);close(chart.yMax,600);check(!chart.changed());
        // A pinch anchored to an off-center point keeps that point stationary.
        double x=chart.xMin+(chart.xMax-chart.xMin)*.25,y=chart.yMin+(chart.yMax-chart.yMin)*.75;
        chart.zoom(2,.25,.75);
        close(chart.xMin+(chart.xMax-chart.xMin)*.25,x);close(chart.yMin+(chart.yMax-chart.yMin)*.75,y);
        close(chart.xMax-chart.xMin,50);close(chart.yMax-chart.yMin,97.5);check(chart.changed());
        double width=chart.xMax-chart.xMin,height=chart.yMax-chart.yMin;
        chart.pan(100,-100);close(chart.xMin,0);close(chart.yMax,1000);close(chart.xMax-chart.xMin,width);close(chart.yMax-chart.yMin,height);
        chart.pan(-100,100);close(chart.xMax,100);close(chart.yMin,200);
        // Extreme zoom never collapses an axis or moves outside the data domain.
        for(int i=0;i<30;i++)chart.zoom(10,.5,.5);
        close(chart.xMax-chart.xMin,.25);close(chart.yMax-chart.yMin,10);
        chart.zoom(.0000001,.5,.5);close(chart.xMin,0);close(chart.xMax,100);close(chart.yMin,200);close(chart.yMax,1000);
        chart.reset();close(chart.yMin,405);close(chart.yMax,600);check(!chart.changed());
        // A redraw must not reset the user's view; invalid gesture factors are ignored.
        chart.zoom(2,.5,.5);double left=chart.xMin;
        chart.configure(0,100,200,1000,405,600);close(chart.xMin,left);
        chart.zoom(Double.NaN,.5,.5);chart.zoom(0,.5,.5);close(chart.xMin,left);
        ChartViewport singleDay=new ChartViewport();singleDay.configure(0,1,200,400,200,400);singleDay.zoom(100,.5,.5);check(singleDay.xMax>singleDay.xMin);
        System.out.println("Chart zoom, pan, bounds, focus anchoring and reset: OK");
    }
}
