package dev.rundashboard.app;

public final class ButtonLayoutTest {
    private static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    private static void inside(int available,int[] widths,int[] heights,ButtonLayout.Plan plan){
        for(int i=0;i<widths.length;i++){
            check(plan.left[i]>=0&&plan.left[i]+widths[i]<=available,"button outside its container");
            check(plan.top[i]+heights[i]<=plan.height,"button height clipped");
            for(int j=0;j<i;j++)check(plan.left[i]>=plan.left[j]+widths[j]||plan.left[j]>=plan.left[i]+widths[i]
                ||plan.top[i]>=plan.top[j]+heights[j]||plan.top[j]>=plan.top[i]+heights[i],"buttons overlap");
        }
    }
    public static void main(String[] args){
        int[] desired={168,180};int[] heights={48,48};
        int[] widths=ButtonLayout.widths(256,desired,8,false);ButtonLayout.Plan plan=ButtonLayout.place(256,widths,heights,8);
        check(plan.top[1]==56,"long chart chips wrap to the next row");inside(256,widths,heights,plan);
        widths=ButtonLayout.widths(400,desired,8,false);plan=ButtonLayout.place(400,widths,heights,8);
        check(plan.top[1]==0,"wide layout keeps chips together");inside(400,widths,heights,plan);
        desired=new int[]{80,110,90};heights=new int[]{48,48,48};
        widths=ButtonLayout.widths(256,desired,8,true);plan=ButtonLayout.place(256,widths,heights,8);
        check(widths[0]==256&&plan.top[2]==112,"segments stack when labels do not fit equally");inside(256,widths,heights,plan);
        widths=ButtonLayout.widths(360,desired,8,true);plan=ButtonLayout.place(360,widths,heights,8);
        check(plan.height==48&&widths[0]==widths[2],"segments share a row when their labels fit");inside(360,widths,heights,plan);
        for(int available:new int[]{160,224,280,360,600})for(int scale:new int[]{1,2,3}){
            desired=new int[]{96*scale,184*scale,120*scale};heights=new int[]{48*scale,64*scale,48*scale};
            for(boolean equal:new boolean[]{false,true}){widths=ButtonLayout.widths(available,desired,8,equal);plan=ButtonLayout.place(available,widths,heights,8);inside(available,widths,heights,plan);}
        }
        System.out.println("Button wrapping, equal-width fallback, narrow screens and enlarged labels: OK");
    }
}
