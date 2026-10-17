package dev.rundashboard.app;

import java.util.ArrayList;

/** Readable ticks in numeric units or seconds; zooming keeps the actual data domain. */
final class ChartAxis {
    static long[] dates(double min,double max,float available,float labelWidth,float gap){
        if(!Double.isFinite(min)||!Double.isFinite(max)||max<=min||available<=0)return new long[0];
        long first=(long)Math.ceil(min),last=(long)Math.floor(max);
        if(last<first)return new long[]{Math.round((min+max)/2)};
        int count=(int)Math.min(last-first+1,Math.max(1,Math.min(4,Math.floor((available+gap)/(labelWidth+gap)))));
        long[] days=new long[count];
        for(int i=0;i<count;i++)days[i]=count==1?Math.round((first+last)/2.0):Math.round(first+(last-first)*i/(double)(count-1));
        return days;
    }
    static double[] ticks(double min,double max,int desired,boolean time){return ticks(min,max,desired,time,0);}
    static double[] ticks(double min,double max,int desired,boolean time,double minimumStep){
        if(!Double.isFinite(min)||!Double.isFinite(max)||max<=min)return new double[0];
        double raw=Math.max(minimumStep,(max-min)/Math.max(2,desired)),step;
        if(time){
            double[] steps={1,2,5,10,15,30,60,120,300,600,900,1800,3600,7200};step=steps[steps.length-1];
            for(double candidate:steps)if(candidate>=raw){step=candidate;break;}
            if(raw>step)step=Math.ceil(raw/3600)*3600;
        }else{
            double magnitude=Math.pow(10,Math.floor(Math.log10(raw)));double scaled=raw/magnitude;
            step=(scaled<=1?1:scaled<=2?2:scaled<=2.5?2.5:scaled<=5?5:10)*magnitude;
        }
        ArrayList<Double> values=new ArrayList<>();
        double first=Math.ceil((min-1e-8)/step)*step;
        for(int i=0;i<12;i++){double value=first+i*step;if(value>max+1e-8)break;values.add(Math.abs(value)<1e-8?0:value);}
        double[] result=new double[values.size()];for(int i=0;i<result.length;i++)result[i]=values.get(i);return result;
    }
}
