package dev.rundashboard.app;

/** Geometry for button groups, using measured text widths rather than font-scale thresholds. */
final class ButtonLayout {
    static int[] widths(int available,int[] preferred,int gap,boolean equal){
        available=Math.max(0,available);int[] widths=new int[preferred.length];
        int slot=preferred.length==0?0:Math.max(0,(available-gap*(preferred.length-1))/preferred.length);
        boolean fits=equal;
        for(int width:preferred)if(width>slot)fits=false;
        for(int i=0;i<widths.length;i++)widths[i]=equal?(fits?slot:available):Math.min(available,Math.max(0,preferred[i]));
        return widths;
    }
    static final class Plan {
        final int[] left,top;
        final int height;
        Plan(int[] left,int[] top,int height){this.left=left;this.top=top;this.height=height;}
    }
    static Plan place(int available,int[] widths,int[] heights,int gap){
        int[] left=new int[widths.length],top=new int[widths.length];int x=0,y=0,rowHeight=0;
        for(int i=0;i<widths.length;i++){
            if(x>0&&x+widths[i]>available){x=0;y+=rowHeight+gap;rowHeight=0;}
            left[i]=x;top[i]=y;x+=widths[i]+gap;rowHeight=Math.max(rowHeight,heights[i]);
        }
        return new Plan(left,top,widths.length==0?0:y+rowHeight);
    }
}
