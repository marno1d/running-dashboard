package dev.rundashboard.app;

/** Select real measurements by date, without interpolating values or mixing series. */
final class ChartScrubber {
    static int nearest(double[] dates,double[] values,String[] identities,String target,double day,
                       double first,double last,double minimum,double maximum){
        return nearest(dates,values,identities,target,day,first,last,minimum,maximum,Double.NaN);
    }
    static int nearest(double[] dates,double[] values,String[] identities,String target,double day,
                       double first,double last,double minimum,double maximum,double fingerValue){
        if(target==null||!Double.isFinite(day))return -1;
        int result=-1;double distance=Double.POSITIVE_INFINITY;
        for(int i=0;i<dates.length;i++){
            if(!Double.isFinite(dates[i])||!Double.isFinite(values[i])||dates[i]<first||dates[i]>last||values[i]<minimum||values[i]>maximum)continue;
            if(!target.isEmpty()&&!target.equals(identities[i]))continue;
            double next=Math.abs(dates[i]-day);
            // Equidistant dates choose the earlier date, regardless of input order.
            if(next<distance||(next==distance&&result>=0&&(dates[i]<dates[result]||
                (dates[i]==dates[result]&&Double.isFinite(fingerValue)&&Math.abs(values[i]-fingerValue)<Math.abs(values[result]-fingerValue))))){result=i;distance=next;}
        }
        return result;
    }
    static double day(float x,float left,float right,double first,double last){
        if(right<=left)return Double.NaN;
        return first+(last-first)*Math.max(0,Math.min(1,(x-left)/(right-left)));
    }
}
