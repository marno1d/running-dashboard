package dev.rundashboard.app;

public final class WorkoutTraceTest {
    static void near(double expected,double actual){if(Math.abs(expected-actual)>.00001)throw new AssertionError(expected+" != "+actual);}
    public static void main(String[] args){
        WorkoutTrace trace=new WorkoutTrace(new double[][]{{0,0,0,100},{100,1,0,120},{200,0,0,100},{300,Double.NaN,Double.NaN,110}},
            new double[][]{{0,100,300,0},{100,150,750,1},{150,200,250,2},{200,300,280,2}},
            new double[]{0,100,150},new double[]{100,150,300},new String[]{"Warm-up","Walking recovery","Rep 1"});
        near(.5,trace.point(50)[1]);near(110,trace.point(50)[3]);
        near(0,trace.point(-20)[0]);near(300,trace.point(500)[0]);
        near(300,trace.pace(99));near(750,trace.pace(100));near(250,trace.pace(150));near(280,trace.pace(300));
        if(trace.step(99)!=0||trace.step(100)!=1||trace.step(150)!=2||trace.step(300)!=2)throw new AssertionError("Incorrect step boundary");
        near(0,trace.point(200)[1]);if(!Double.isNaN(trace.point(250)[1]))throw new AssertionError("Invented GPS extrapolation");near(105,trace.point(250)[3]);
        System.out.println("Shared cursor interpolation, phase boundaries, recoveries and GPS gaps: OK");
    }
}
