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
        desired=new int[]{50,67,64,40};heights=new int[]{36,36,36,36};
        widths=ButtonLayout.metricWidths(296,desired,8);plan=ButtonLayout.place(296,widths,heights,8);
        check(plan.height==36,"normal session metrics fit on one compact row");inside(296,widths,heights,plan);
        desired=new int[]{100,134,128,80};
        widths=ButtonLayout.metricWidths(296,desired,8);plan=ButtonLayout.place(296,widths,heights,8);
        check(plan.top[1]==0&&plan.top[2]==44,"enlarged metrics use two columns instead of truncating");inside(296,widths,heights,plan);
        desired=new int[]{150,201,192,120};
        widths=ButtonLayout.metricWidths(296,desired,8);plan=ButtonLayout.place(296,widths,heights,8);
        check(plan.top[3]==132,"very large metric labels stack");inside(296,widths,heights,plan);
        for(int available:new int[]{0,160,224,280,360,600})for(int scale:new int[]{1,2,3}){
            desired=new int[]{50*scale,67*scale,64*scale,40*scale};heights=new int[]{36*scale,36*scale,36*scale,36*scale};
            widths=ButtonLayout.metricWidths(available,desired,8);plan=ButtonLayout.place(available,widths,heights,8);inside(available,widths,heights,plan);
        }
        // Both session rows share one grid: work pace/HR occupy slots 5 and 7.
        for(int available:new int[]{160,224,296,360,600})for(int scale:new int[]{1,2,3}){
            desired=new int[]{50*scale,67*scale,64*scale,40*scale,58*scale,40*scale,0,32*scale};
            heights=new int[]{36*scale,36*scale,36*scale,36*scale,19*scale,19*scale,0,19*scale};
            widths=ButtonLayout.metricWidths(available,desired,8);plan=ButtonLayout.place(available,widths,heights,8);
            inside(available,widths,heights,plan);
            check(plan.left[1]==plan.left[5],"overall and interval pace columns must align");
            check(plan.left[3]==plan.left[7],"overall and interval HR columns must align");
            check(plan.top[5]>plan.top[1]&&plan.top[7]>plan.top[3],"work values follow overall values");
            if(available>=296&&scale==1){
                check(plan.top[0]==plan.top[3]&&plan.top[4]==plan.top[7],"two session rows stay compact on a normal screen");
                check(plan.top[4]>plan.top[0],"wide screens must not collapse both rows into eight columns");
            }
        }
        check(ButtonLayout.metricWidths(280,new int[0],8).length==0,"empty metric row");
        System.out.println("Button wrapping and compact aligned overall/work metrics on narrow screens and enlarged labels: OK");
    }
}
