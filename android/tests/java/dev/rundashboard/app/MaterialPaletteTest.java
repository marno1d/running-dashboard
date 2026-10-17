package dev.rundashboard.app;

/** Verify legibility of real UI roles in both themes, including translucent chart markers. */
public final class MaterialPaletteTest {
    private static double channel(int value){double s=value/255.0;return s<=.04045?s/12.92:Math.pow((s+.055)/1.055,2.4);}
    private static double luminance(int color){return .2126*channel((color>>16)&255)+.7152*channel((color>>8)&255)+.0722*channel(color&255);}
    private static double contrast(int first,int second){double a=luminance(first),b=luminance(second);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);}
    private static int composite(int foreground,int background){
        int value=0xff000000;for(int shift=0;shift<=16;shift+=8)value|=(((((foreground>>shift)&255)*210+((background>>shift)&255)*45)/255)<<shift);return value;
    }
    private static void check(int foreground,int background,double minimum,String label){
        double ratio=contrast(foreground,background);if(ratio<minimum)throw new AssertionError(label+" contrast "+ratio+" < "+minimum);
    }
    public static void main(String[] args){
        for(boolean dark:new boolean[]{false,true}){
            MaterialPalette p=new MaterialPalette(dark);String theme=dark?"dark":"light";
            for(int surface:new int[]{p.surface,p.container,p.high}){
                check(p.ink,surface,4.5,theme+" body text");check(p.muted,surface,4.5,theme+" secondary text");
                check(p.primary,surface,4.5,theme+" actions");check(p.error,surface,4.5,theme+" errors");
            }
            check(p.onPrimary,p.primary,4.5,theme+" filled buttons");
            check(p.onPrimaryContainer,p.primaryContainer,4.5,theme+" pace cards and selected navigation");
            for(int color:MaterialPalette.SERIES)check(composite(p.chart(color),p.container),p.container,3,theme+" chart marker");
        }
        System.out.println("Material light/dark text, controls, selected states and chart contrast: OK");
    }
}
