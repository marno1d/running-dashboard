package dev.rundashboard.app;

/** Distance is the shared cursor for GPS, elevation, workout steps and pace. */
final class WorkoutTrace {
    final double[][] nodes,paces;
    final double[] starts,ends;
    final String[] labels;
    final double distance;
    WorkoutTrace(double[][] nodes,double[][] paces,double[] starts,double[] ends,String[] labels){
        this.nodes=nodes;this.paces=paces;this.starts=starts;this.ends=ends;this.labels=labels;
        distance=nodes[nodes.length-1][0];
    }
    double clamp(double at){return Math.max(0,Math.min(distance,at));}
    private int interval(double[][] rows,double at){
        int lo=0,hi=rows.length-1;
        while(lo<hi){int mid=(lo+hi+1)/2;if(rows[mid][0]<=at)lo=mid;else hi=mid-1;}
        return lo;
    }
    double[] point(double at){
        at=clamp(at);int i=Math.min(nodes.length-2,interval(nodes,at));double[] a=nodes[i],b=nodes[i+1];
        double fraction=(at-a[0])/Math.max(.000001,b[0]-a[0]);double[] result={at,Double.NaN,Double.NaN,a[3]+(b[3]-a[3])*fraction};
        for(int j=1;j<=2;j++)result[j]=fraction<=1e-8?a[j]:fraction>=1-1e-8?b[j]:a[j]+(b[j]-a[j])*fraction;
        return result;
    }
    double pace(double at){return paces[interval(paces,clamp(at))][2];}
    int step(double at){
        at=clamp(at);
        for(int i=0;i<ends.length;i++)if(ends[i]>starts[i]&&(at<ends[i]||i==ends.length-1))return i;
        return Math.max(0,ends.length-1);
    }
}
