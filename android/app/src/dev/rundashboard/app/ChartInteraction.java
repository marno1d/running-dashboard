package dev.rundashboard.app;

/** Gesture and missing-data rules, independent of Android drawing. */
final class ChartInteraction {
    // A chart owns horizontal drags only; vertical movement belongs to the page.
    static int direction(float dx,float dy,int slop){
        if(Math.max(Math.abs(dx),Math.abs(dy))<=slop)return 0;
        return Math.abs(dx)>Math.abs(dy)?1:-1;
    }
    static boolean adjacentWeeks(long previous,long current){return current-previous==7;}
}
