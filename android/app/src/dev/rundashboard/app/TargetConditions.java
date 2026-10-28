package dev.rundashboard.app;

/** Validate inline edits before replacing the last complete set of conditions. */
final class TargetConditions {
    static final String[] KEYS={"target_temperature","target_humidity","target_gain_per_mile","target_loss_per_mile"};
    static final String[] DEFAULTS={"45","","0.0","0.0"};
    static String canonical(int field,String text){
        text=text.trim();if(field<2)return text;
        double value=text.isEmpty()?0:Double.parseDouble(text);
        return String.format(java.util.Locale.ROOT,"%.1f",Math.max(0,value));
    }
    static boolean valid(int field,String text){
        if(text.trim().isEmpty())return true;
        try{double n=Double.parseDouble(text.trim());return Double.isFinite(n)&&(field!=1||n>=0&&n<=100)&&(field<2||n>=0);}
        catch(NumberFormatException error){return false;}
    }
}
