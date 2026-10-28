package dev.rundashboard.app;

import android.app.Activity;
import android.app.ActivityManager;
import android.app.ApplicationExitInfo;
import android.app.AlertDialog;
import android.net.Uri;
import android.os.Bundle;
import android.widget.*;
import org.json.JSONObject;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** Diagnostics opens independently of Garmin/Python, including after a startup crash. */
public final class DiagnosticsActivity extends Activity {
    private String report(){
        StringBuilder text=new StringBuilder(AppErrorLog.report());
        if(android.os.Build.VERSION.SDK_INT>=30)try{
            ActivityManager manager=(ActivityManager)getSystemService(ACTIVITY_SERVICE);
            for(ApplicationExitInfo exit:manager.getHistoricalProcessExitReasons(getPackageName(),0,3))
                text.append("\nPrevious process exit: reason=").append(exit.getReason()).append(" · epoch ms=").append(exit.getTimestamp())
                    .append(" · PSS KiB=").append(exit.getPss()).append(" · RSS KiB=").append(exit.getRss());
        }catch(Exception ignored){}
        return text.toString();
    }
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);getWindow().setFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE,android.view.WindowManager.LayoutParams.FLAG_SECURE);
        LinearLayout body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);int pad=(int)(20*getResources().getDisplayMetrics().density);body.setPadding(pad,pad,pad,pad);
        body.setOnApplyWindowInsetsListener((view,insets)->{view.setPadding(pad,pad+insets.getSystemWindowInsetTop(),pad,pad+insets.getSystemWindowInsetBottom());return insets.consumeSystemWindowInsets();});
        TextView title=new TextView(this);title.setText("Error report");title.setTextSize(24);body.addView(title);
        TextView status=new TextView(this);status.setText("Technical error locations and memory/exit information. Credentials, coordinates and exception messages are excluded.");body.addView(status);
        ScrollView scroll=new ScrollView(this);TextView contents=new TextView(this);contents.setText(report());contents.setTextIsSelectable(true);contents.setTextSize(12);scroll.addView(contents);body.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        Uri uri=getIntent().getData();String token=uri==null?null:uri.getQueryParameter("token");int supplied=0;
        try{supplied=Integer.parseInt(uri.getQueryParameter("port"));}catch(Exception ignored){}
        final int port=supplied;
        if(port>=1024&&port<=65535&&token!=null&&token.matches("[A-Za-z0-9_-]{24,128}")){
            Button share=new Button(this);share.setText("Share error report locally");body.addView(share);
            share.setOnClickListener(view->new AlertDialog.Builder(this).setTitle("Share error report?").setMessage("Send the technical report shown here directly to the local development project on this phone?")
                .setNegativeButton("Cancel",null).setPositiveButton("Share",(dialog,which)->{
                    share.setEnabled(false);status.setText("Sharing locally…");final String details=report();
                    new Thread(()->{
                        boolean success=false;
                        try{
                            JSONObject payload=new JSONObject().put("schema",1).put("kind","diagnostics").put("report",details)
                                .put("android_api",android.os.Build.VERSION.SDK_INT).put("max_heap_mb",Runtime.getRuntime().maxMemory()/1048576);
                            byte[] bytes=payload.toString().getBytes(StandardCharsets.UTF_8);
                            HttpURLConnection connection=(HttpURLConnection)new URL("http://127.0.0.1:"+port+"/diagnostics/"+token).openConnection();
                            connection.setConnectTimeout(10000);connection.setReadTimeout(10000);connection.setInstanceFollowRedirects(false);
                            try{connection.setRequestMethod("POST");connection.setDoOutput(true);connection.setRequestProperty("Content-Type","application/json");try(java.io.OutputStream output=connection.getOutputStream()){output.write(bytes);}success=connection.getResponseCode()==200;}finally{connection.disconnect();}
                        }catch(Exception error){AppErrorLog.record("diagnostics.share",error);}
                        final boolean sent=success;runOnUiThread(()->{status.setText(sent?"Error report shared. Return to the chat.":"Could not reach the local receiver. Reopen the sharing page and retry.");share.setEnabled(true);});
                    },"local-diagnostics").start();
                }).show());
        }
        Button close=new Button(this);close.setText("Close");close.setOnClickListener(view->finish());body.addView(close);setContentView(body);
    }
}
