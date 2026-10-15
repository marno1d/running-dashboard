package dev.rundashboard.app;

/** Chart coordinates only: no Android dependency, shared by gestures and drawing. */
final class ChartViewport {
    double xMin,xMax,yMin,yMax;
    private double domainXMin,domainXMax,domainYMin,domainYMax,initialYMin,initialYMax;
    private boolean configured;
    void configure(double left,double right,double top,double bottom,double initialTop,double initialBottom){
        if(configured)return;
        domainXMin=left;domainXMax=right;domainYMin=top;domainYMax=bottom;
        initialYMin=initialTop;initialYMax=initialBottom;configured=true;reset();
    }
    boolean ready(){return configured;}
    void reset(){if(!configured)return;xMin=domainXMin;xMax=domainXMax;yMin=initialYMin;yMax=initialYMax;}
    boolean changed(){return configured&&(Math.abs(xMin-domainXMin)>1e-7||Math.abs(xMax-domainXMax)>1e-7||Math.abs(yMin-initialYMin)>1e-7||Math.abs(yMax-initialYMax)>1e-7);}
    void zoom(double factor,double xFraction,double yFraction){
        if(!configured||!Double.isFinite(factor)||factor<=0)return;
        xFraction=Math.max(0,Math.min(1,xFraction));yFraction=Math.max(0,Math.min(1,yFraction));
        double anchorX=xMin+(xMax-xMin)*xFraction,anchorY=yMin+(yMax-yMin)*yFraction;
        double width=Math.max(Math.min(.25,domainXMax-domainXMin),Math.min(domainXMax-domainXMin,(xMax-xMin)/factor));
        double height=Math.max(Math.min(10,domainYMax-domainYMin),Math.min(domainYMax-domainYMin,(yMax-yMin)/factor));
        xMin=anchorX-width*xFraction;xMax=xMin+width;yMin=anchorY-height*yFraction;yMax=yMin+height;clamp();
    }
    void pan(double xFraction,double yFraction){
        if(!configured)return;
        double dx=xFraction*(xMax-xMin),dy=yFraction*(yMax-yMin);
        xMin-=dx;xMax-=dx;yMin-=dy;yMax-=dy;clamp();
    }
    private void clamp(){
        if(xMin<domainXMin){xMax+=domainXMin-xMin;xMin=domainXMin;}
        if(xMax>domainXMax){xMin-=xMax-domainXMax;xMax=domainXMax;}
        if(yMin<domainYMin){yMax+=domainYMin-yMin;yMin=domainYMin;}
        if(yMax>domainYMax){yMin-=yMax-domainYMax;yMax=domainYMax;}
    }
}
