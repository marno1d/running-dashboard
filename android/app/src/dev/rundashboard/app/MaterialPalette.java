package dev.rundashboard.app;

/** Shared Material 3 color roles. Chart series retain their semantic hues. */
final class MaterialPalette {
    static final int[] SERIES={0xff397c3a,0xff725ca8,0xff3f6fa8,0xff287c71,0xffb34e4e,0xff66736d,0xff96621b,0xff96621b,0xff725ca8,0xff66736d,0xff3f6fa8,0xffb34e4e,0xff66736d};
    final boolean dark;
    final int primary,onPrimary,primaryContainer,onPrimaryContainer,surface,container,high,
        ink,muted,outline,error,errorContainer;
    MaterialPalette(boolean dark){
        this.dark=dark;
        primary=dark?0xff81d5c2:0xff006b5e;onPrimary=dark?0xff00382f:0xffffffff;
        primaryContainer=dark?0xff005045:0xff9df2de;onPrimaryContainer=dark?0xff9df2de:0xff00201b;
        surface=dark?0xff101513:0xfff7faf7;container=dark?0xff1b211e:0xffeef3ef;
        high=dark?0xff252d29:0xffe5ebe7;ink=dark?0xffdfe5df:0xff17201c;
        muted=dark?0xffb5c9bd:0xff4f635a;outline=dark?0xff3e4d44:0xffbac8c0;
        error=dark?0xffffb4ab:0xffba1a1a;errorContainer=dark?0xff690005:0xffffdad6;
    }
    int chart(int color){
        if(!dark)return color;
        int red=(color>>16)&255,green=(color>>8)&255,blue=color&255;
        return 0xff000000|((red+(255-red)*40/100)<<16)|((green+(255-green)*40/100)<<8)|(blue+(255-blue)*40/100);
    }
}
