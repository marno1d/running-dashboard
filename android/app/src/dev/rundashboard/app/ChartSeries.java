package dev.rundashboard.app;

/** Stable legend identities and visibility; independent of drawing and Android preferences. */
final class ChartSeries {
    static final String NONE="",PREDICTION="prediction",INTERVAL="interval",EASY="easy",HEART="heart";
    final String mode;
    final String[] ids,labels,colors;
    final int[] markers;
    private final boolean[] visible;

    ChartSeries(String mode){
        this.mode=mode;
        switch(mode){
            case PREDICTION:
                ids=new String[]{"trial","prediction","easy_prediction"};labels=new String[]{"Measured","Intervals","Easy"};
                colors=new String[]{"trial","prediction","easy_prediction"};markers=new int[]{1,2,3};break;
            case INTERVAL:
                ids=new String[]{"short","medium","long"};labels=new String[]{"Short","Medium","Long"};
                colors=new String[]{"short","medium","long"};markers=new int[]{2,3,0};break;
            case EASY:
                ids=new String[]{"road","trail"};labels=new String[]{"Road / treadmill","Trail"};
                colors=new String[]{"easy","easy"};markers=new int[]{0,4};break;
            case HEART:
                ids=new String[]{"high","middle","low"};labels=new String[]{"≥90% below","75–89%","<75%"};
                colors=new String[]{"easy","cross_train","trial"};markers=new int[]{0,0,0};break;
            default:
                ids=new String[0];labels=new String[0];colors=new String[0];markers=new int[0];
        }
        visible=new boolean[ids.length];java.util.Arrays.fill(visible,true);
    }
    String seriesId(String category,String activityType,double belowCeiling){
        if(EASY.equals(mode))return "trail_running".equals(activityType)?"trail":"road";
        if(HEART.equals(mode))return belowCeiling>=90?"high":belowCeiling>=75?"middle":"low";
        return category;
    }
    boolean isVisible(String id){
        for(int i=0;i<ids.length;i++)if(ids[i].equals(id))return visible[i];return true;
    }
    void setVisible(String id,boolean shown){for(int i=0;i<ids.length;i++)if(ids[i].equals(id))visible[i]=shown;}
    boolean pointVisible(String category,String activityType,double belowCeiling){return isVisible(seriesId(category,activityType,belowCeiling));}
    boolean anyVisible(){for(boolean shown:visible)if(shown)return true;return ids.length==0;}
    // Empty identity means a chart with no legend; null means every item is off.
    String firstVisible(){for(int i=0;i<ids.length;i++)if(visible[i])return ids[i];return ids.length==0?"":null;}
    String labelFor(String id){for(int i=0;i<ids.length;i++)if(ids[i].equals(id))return labels[i];return "";}
    String preferenceKey(String id){
        if(PREDICTION.equals(mode)){
            if("trial".equals(id))return "show_trial_points";
            if("prediction".equals(id))return "show_prediction_points";
            if("easy_prediction".equals(id))return "show_easy_prediction_points";
        }
        return "chart_series_"+mode+"_"+id;
    }
}
