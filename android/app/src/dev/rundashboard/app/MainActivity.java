package dev.rundashboard.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import android.os.Bundle;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.text.InputType;
import android.view.View;
import android.view.WindowManager;
import android.widget.*;
import com.chaquo.python.Python;
import com.chaquo.python.PyObject;
import com.chaquo.python.android.AndroidPlatform;
import java.time.LocalDate;
import android.text.Editable;
import android.text.TextWatcher;
import android.text.TextUtils;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONObject;
import org.json.JSONArray;

public final class MainActivity extends Activity {
    private static final ExecutorService WORKER = Executors.newSingleThreadExecutor();
    private final int ink=Color.rgb(31,39,35), muted=Color.rgb(102,115,109);
    private LinearLayout root, content, rangeBar, adjustBar, navigation, runList;
    private final StringBuilder syncLog=new StringBuilder();
    private TextView logView;
    private Button logButton;
    private ScrollView scroll;
    private TextView heading;
    private final Button[] tabs=new Button[3];
    private int screen, visibleRuns=30;
    private final int[] scrollPositions=new int[3];
    private String runFilter="all", query="";
    private TextView message;
    private SessionStore store;
    private PyObject backend;
    private boolean busy, authenticated, needsMfa, profileOpen, profileDirty;
    private Button refreshButton;
    private ProgressBar downloadProgress;
    public interface ProgressSink { void update(String label,int completed,int total); }
    private JSONObject dashboardData;
    private android.content.SharedPreferences preferences;
    private int days;
    private boolean miles;
    private Uri pendingSample;
    private JSONObject settings() throws Exception {
        JSONObject state=new JSONObject(preferences.getString("settings","{}"));
        state.put("easy_hr",preferences.getInt("easy_hr",134));
        state.put("interval_mode",preferences.getString("interval_mode",state.optString("interval_mode","session")));
        state.put("max_hr",preferences.getInt("max_hr",191));
        state.put("include_recovery",preferences.getBoolean("include_recovery",true));
        state.put("include_recordings",preferences.getBoolean("include_recordings",true));
        state.put("include_weather",preferences.getBoolean("include_weather",true));
        state.put("include_station_weather",preferences.getBoolean("include_station_weather",true));
        state.put("include_terrain",preferences.getBoolean("include_terrain",false));
        state.put("full_history",preferences.getBoolean("full_history",true));
        state.put("custom_range",days==-1);
        if(!state.has("classification_mode"))state.put("classification_mode","web");
        return state;
    }
    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);setIntent(intent);
        pendingSample=intent.getData();handleSampleRequest();
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_SECURE,WindowManager.LayoutParams.FLAG_SECURE);
        getWindow().setStatusBarColor(Color.rgb(246,247,244));
        getWindow().setNavigationBarColor(Color.rgb(246,247,244));
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        store=new SessionStore(getApplicationContext());
        preferences=getSharedPreferences("training",0);
        days=preferences.getInt("days",0);miles=preferences.getBoolean("miles",true);
        pendingSample=getIntent().getData();
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(246,247,244));setContentView(root);
        root.setOnApplyWindowInsetsListener((view,insets)-> {
            view.setPadding(0,insets.getSystemWindowInsetTop(),0,insets.getSystemWindowInsetBottom());
            return insets.consumeSystemWindowInsets();
        });
        LinearLayout header=new LinearLayout(this);header.setGravity(android.view.Gravity.CENTER_VERTICAL);
        header.setPadding(dp(20),dp(10),dp(16),dp(8));
        LinearLayout titles=new LinearLayout(this);titles.setOrientation(LinearLayout.VERTICAL);
        heading=addText(titles,"Training dashboard",24,ink,true,0);
        addText(titles,"NORWEGIAN SINGLES PROGRESS",10,muted,true,3);
        header.addView(titles,new LinearLayout.LayoutParams(0,-2,1));
        refreshButton=actionButton("Refresh",true,this::loadRuns);
        header.addView(refreshButton,new LinearLayout.LayoutParams(dp(96),dp(48)));root.addView(header);
        rangeBar=new LinearLayout(this);rangeBar.setPadding(dp(16),dp(6),dp(16),dp(4));root.addView(rangeBar);
        adjustBar=new LinearLayout(this);adjustBar.setPadding(dp(16),0,dp(16),0);root.addView(adjustBar);
        LinearLayout status=new LinearLayout(this);status.setPadding(dp(20),dp(4),dp(20),dp(6));
        message=text("Starting…",12,muted,false);message.setMaxLines(3);
        message.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        status.addView(message,new LinearLayout.LayoutParams(0,-2,1));
        logButton=actionButton("Log",false,this::showSyncLog);logButton.setTextSize(12);logButton.setOnClickListener(v->showSyncLog());status.addView(logButton,new LinearLayout.LayoutParams(dp(60),dp(48)));root.addView(status);
        downloadProgress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);
        downloadProgress.setIndeterminateTintList(android.content.res.ColorStateList.valueOf(ink));
        downloadProgress.setProgressTintList(android.content.res.ColorStateList.valueOf(ink));
        root.addView(downloadProgress,new LinearLayout.LayoutParams(-1,dp(3)));downloadProgress.setVisibility(View.GONE);
        scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setClipToPadding(false);
        content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(16),dp(8),dp(16),dp(24));scroll.addView(content);
        root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        navigation=new LinearLayout(this);navigation.setPadding(dp(12),dp(8),dp(12),dp(8));navigation.setBackgroundColor(Color.WHITE);
        String[] names={"Trends","Sessions","Profile"};
        for(int i=0;i<3;i++){
            final int tab=i;tabs[i]=actionButton(names[i],false,()->selectScreen(tab));
            tabs[i].setOnClickListener(v->selectScreen(tab));
            LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,dp(48),1);lp.setMargins(dp(4),0,dp(4),0);navigation.addView(tabs[i],lp);
        }
        root.addView(navigation);updateChrome();
        execute("Starting the app…",()-> {
            System.loadLibrary("android-support");
            System.loadLibrary("ffi");
            System.loadLibrary("c++_shared-d523468d");
            if(!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
            backend=Python.getInstance().getModule("garmin_backend");
            invoke("configure_cache",new java.io.File(getFilesDir(),"run-cache.sqlite").getAbsolutePath());
            JSONObject saved;
            try { saved=store.load(); }
            catch(Exception error) { store.clear(); saved=null; }
            return invoke("restore",saved==null ? "" : saved.toString());
        },result-> {
            render(result);
            if(authenticated) loadDashboard(false);
        });
    }
    private int dp(int value) {return (int)(value*getResources().getDisplayMetrics().density+.5f);}
    private GradientDrawable shape(int color,int radius) {GradientDrawable d=new GradientDrawable(); d.setColor(color); d.setCornerRadius(dp(radius)); return d;}
    private TextView text(String value,int size,int color,boolean bold) {
        TextView v=new TextView(this); v.setText(value); v.setTextSize(size); v.setTextColor(color);
        v.setTypeface(Typeface.create("sans-serif",bold?Typeface.BOLD:Typeface.NORMAL)); return v;
    }
    private TextView addText(LinearLayout parent,String value,int size,int color,boolean bold,int top) {
        TextView v=text(value,size,color,bold); LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2); lp.topMargin=dp(top); parent.addView(v,lp); return v;
    }
    private EditText input(String label,int type) {return input(content,label,type);}
    private EditText input(LinearLayout parent,String label,int type) {
        addText(parent,label,13,ink,true,18);
        EditText field=new EditText(this); field.setSingleLine(true); field.setInputType(type); field.setTextColor(ink);
        field.setSaveEnabled(false); field.setTextSize(16); field.setPadding(dp(12),dp(12),dp(12),dp(12)); field.setBackground(shape(Color.rgb(244,246,240),10));
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,dp(52)); lp.topMargin=dp(8); parent.addView(field,lp); return field;
    }
    private Button actionButton(String title,boolean primary,Runnable action) {
        Button b=new Button(this);b.setText(title);b.setAllCaps(false);b.setTextSize(14);b.setMinHeight(dp(48));
        b.setTextColor(primary?Color.WHITE:ink);b.setBackground(shape(primary?Color.rgb(40,124,113):Color.rgb(237,242,235),8));
        b.setOnClickListener(v->{if(!busy)action.run();});return b;
    }
    private Button button(String title,boolean primary,Runnable action) {return button(content,title,primary,action);}
    private Button button(LinearLayout parent,String title,boolean primary,Runnable action) {
        Button b=actionButton(title,primary,action);
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,dp(52));lp.topMargin=dp(12);parent.addView(b,lp);return b;
    }
    private LinearLayout card() {
        LinearLayout panel=new LinearLayout(this);panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(16),dp(16),dp(16),dp(16));panel.setBackground(panelShape());panel.setElevation(dp(1));
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.bottomMargin=dp(12);content.addView(panel,lp);return panel;
    }
    private GradientDrawable panelShape(){GradientDrawable shape=shape(Color.WHITE,8);shape.setStroke(dp(1),Color.rgb(223,228,220));return shape;}
    private void showSyncLog(){
        logView=text(syncLog.toString(),12,ink,false);logView.setPadding(dp(16),dp(12),dp(16),dp(12));logView.setTextIsSelectable(true);
        ScrollView logs=new ScrollView(this);logs.addView(logView);
        new AlertDialog.Builder(this).setTitle(busy?"Updating dashboard…":"Update log").setView(logs).setPositiveButton("Close",(d,w)->logView=null).setOnDismissListener(d->logView=null).show();
    }
    private void recordProgress(String label){
        syncLog.append(label).append('\n');if(syncLog.length()>20000)syncLog.delete(0,syncLog.length()-16000);
        if(logView!=null)logView.setText(syncLog.toString());if(logButton!=null)logButton.setVisibility(View.VISIBLE);
    }
    private void updateChrome() {
        heading.setText(screen==2?"Profile":screen==1?"Sessions":"Training dashboard");
        refreshButton.setVisibility(authenticated&&screen!=2?View.VISIBLE:View.GONE);
        refreshButton.setEnabled(!busy);rangeBar.setVisibility(authenticated&&screen!=2?View.VISIBLE:View.GONE);
        if(logButton!=null)logButton.setVisibility(syncLog.length()>0?View.VISIBLE:View.GONE);
        adjustBar.setVisibility(authenticated&&screen!=2?View.VISIBLE:View.GONE);adjustBar.removeAllViews();
        String[] adjustKeys={"all","adjust_elevation","adjust_temperature"};String[] adjustLabels={"All","Elevation","Temp"};
        for(int i=0;i<adjustKeys.length;i++){
            final String key=adjustKeys[i];CheckBox box=new CheckBox(this);box.setText(adjustLabels[i]);box.setTextSize(13);box.setTextColor(ink);
            box.setChecked(key.equals("all")?"true".equals(setting("adjust_elevation","false"))&&"true".equals(setting("adjust_temperature","false")):"true".equals(setting(key,"false")));
            box.setEnabled(!busy);adjustBar.addView(box,new LinearLayout.LayoutParams(0,dp(44),1));
            box.setOnCheckedChangeListener((view,checked)->{if(busy)return;if(key.equals("all")){saveSetting("adjust_elevation",checked);saveSetting("adjust_temperature",checked);}else saveSetting(key,checked);loadDashboard(false);});
        }
        rangeBar.removeAllViews();int[] windows={0,7,30,45,90,180,365,548,730,-1};
        String[] labels={"All (since June 2025)","Last 7 days","Last 30 days","Last 45 days","Last 90 days","Last 180 days","Last year","Last 18 months","Last 24 months","Custom dates…"};
        int selected=4;for(int i=0;i<windows.length;i++)if(days==windows[i])selected=i;
        final int chosen=selected;
        Button range=actionButton(labels[selected]+" ▾",false,()->new AlertDialog.Builder(this).setTitle("Date range")
            .setSingleChoiceItems(labels,chosen,(dialog,which)->{dialog.dismiss();if(windows[which]==-1)chooseDates();else changeRange(windows[which]);}).setNegativeButton("Cancel",null).show());
        range.setEnabled(!busy);rangeBar.addView(range,new LinearLayout.LayoutParams(0,dp(48),1));
        TextView units=text(miles?"min/mile":"min/km",12,muted,true);units.setGravity(android.view.Gravity.CENTER);
        rangeBar.addView(units,new LinearLayout.LayoutParams(dp(88),dp(48)));
        for(int i=0;i<tabs.length;i++){
            tabs[i].setTextColor(screen==i?Color.WHITE:muted);tabs[i].setBackground(shape(screen==i?ink:Color.WHITE,12));
            tabs[i].setSelected(screen==i);tabs[i].setEnabled(true);
        }
    }
    private void changeRange(int range) {
        if(days==range)return;days=range;preferences.edit().putInt("days",days).apply();updateChrome();loadDashboard(false);
    }
    private void selectScreen(int target) {
        if(target==screen)return;
        scrollPositions[screen]=scroll.getScrollY();screen=target;profileOpen=screen==2;
        android.view.inputmethod.InputMethodManager keyboard=(android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE);
        keyboard.hideSoftInputFromWindow(content.getWindowToken(),0);
        if(profileOpen)renderProfile();else if(authenticated)renderRuns(null);else renderWelcome();
        if(busy)enable(content,false);
        scroll.post(()->scroll.scrollTo(0,scrollPositions[screen]));
        if(!busy&&authenticated&&screen!=2&&profileDirty)loadDashboard(false);
    }
    private void render(JSONObject state) {
        authenticated=state.optBoolean("authenticated");needsMfa=state.optBoolean("needs_mfa");
        if(needsMfa){screen=2;profileOpen=true;}
        if(profileOpen)renderProfile();else if(authenticated)renderRuns(null);else renderWelcome();
    }
    private void renderWelcome() {
        content.removeAllViews();updateChrome();LinearLayout panel=card();
        addText(panel,"Your training, over time",26,ink,true,0);
        addText(panel,"Track easy-run pace, compare your intervals, and follow your 5K times.",16,muted,false,12);
        Button connect=actionButton("Connect Garmin",true,()->selectScreen(2));
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,dp(52));lp.topMargin=dp(24);panel.addView(connect,lp);
        addText(panel,"Sign in once. Your session stays on this phone.",12,muted,false,12);
    }
    private void renderAuthentication(LinearLayout parent) {
        if(needsMfa) {
            addText(parent,"Verify your sign-in",23,ink,true,0);
            addText(parent,"Enter the code from Garmin's email, text message, or your authenticator.",14,muted,false,12);
            EditText code=input(parent,"Verification code",InputType.TYPE_CLASS_NUMBER);
            button(parent,"Verify and load runs",true,()-> {
                String value=code.getText().toString().trim();
                if(value.isEmpty()){message.setText("Enter your verification code.");return;}
                execute("Verifying your code…",()->invoke("verify",value),result->{code.setText("");render(result);if(authenticated){profileOpen=false;screen=0;renderRuns(null);loadRuns();}});
            });
            button(parent,"Start sign-in again",false,this::logout);
        } else {
            addText(parent,"Connect Garmin",23,ink,true,0);
            addText(parent,"Sign in with your Garmin Connect account.",14,muted,false,12);
            EditText email=input(parent,"Email",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);
            EditText password=input(parent,"Password",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
            button(parent,"Sign in to Garmin  ↗",true,()-> {
                String user=email.getText().toString().trim(), pass=password.getText().toString();
                if(user.isEmpty()||pass.isEmpty()){message.setText("Enter your Garmin email and password.");return;}
                password.setText("");
                execute("Signing in to Garmin. This may take a minute…",()->{store.clear();return invoke("login",user,pass);},result->{render(result);if(authenticated){profileOpen=false;screen=0;renderRuns(null);loadRuns();}});
            });
            addText(parent,"Your password goes to Garmin over HTTPS and isn't saved. Your session is encrypted on this phone. Personal prototype using an unofficial Garmin connection.",12,muted,false,20);
        }
    }
    @Override public void onBackPressed(){
        if(screen!=0){selectScreen(0);return;}
        super.onBackPressed();
    }
    private void renderProfile() {
        profileOpen=true;screen=2;content.removeAllViews();updateChrome();
        LinearLayout account=card();
        if(authenticated){
            addText(account,"Garmin Connect",19,ink,true,0);
            addText(account,"● Connected",14,ScatterPlot.color("easy"),true,8);
            button(account,"Sign out",false,()->new AlertDialog.Builder(this).setTitle("Sign out of Garmin?")
                .setMessage("This removes your saved Garmin session, downloaded runs and run corrections from this phone. Your display settings are kept.")
                .setNegativeButton("Cancel",null).setPositiveButton("Sign out",(d,w)->logout()).show());
        }else renderAuthentication(account);
        LinearLayout display=card();addText(display,"Display",19,ink,true,0);
        addText(display,"Pace & distance units",13,ink,true,16);
        Spinner units=new Spinner(this);
        units.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"Minutes per mile · miles","Minutes per kilometre · km"}));
        units.setSelection(miles?0:1);display.addView(units,new LinearLayout.LayoutParams(-1,dp(48)));
        units.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){
            public void onNothingSelected(AdapterView<?> parent){}
            public void onItemSelected(AdapterView<?> parent,View view,int position,long id){
                boolean useMiles=position==0;if(!busy&&miles!=useMiles){miles=useMiles;preferences.edit().putBoolean("miles",miles).apply();message.setText("Display units saved.");}
            }
        });
        addText(display,"Interval dots",13,ink,true,16);
        Spinner mode=new Spinner(this);mode.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"Each work interval","Session average"}));
        boolean average=false;try{average="session".equals(settings().optString("interval_mode"));}catch(Exception ignored){}
        mode.setSelection(average?1:0);display.addView(mode,new LinearLayout.LayoutParams(-1,dp(48)));
        mode.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){
            public void onNothingSelected(AdapterView<?> parent){}
            public void onItemSelected(AdapterView<?> parent,View view,int position,long id){
                try{String chosen=position==1?"session":"rep";if(!busy&&!chosen.equals(settings().optString("interval_mode"))){preferences.edit().putString("interval_mode",chosen).apply();profileDirty=true;message.setText("Interval view saved.");}}catch(Exception ignored){}
            }
        });
        addText(display,"5K times always use minutes:seconds.",12,muted,false,12);
        LinearLayout sync=card();addText(sync,"Dashboard data",19,ink,true,0);
        String[] syncKeys={"full_history","include_recovery","include_weather","include_station_weather","include_recordings","include_terrain"};String[] syncLabels={"Use full history for predictions and targets","Download sleep, resting HR & HRV","Download Garmin activity weather","Prefer nearby KPVU / KSLC station weather","Read original FIT interval and HR metrics","Terrain elevation: send sampled routes to OpenTopoData"};
        for(int i=0;i<syncKeys.length;i++){
            final String key=syncKeys[i];CheckBox choice=new CheckBox(this);choice.setText(syncLabels[i]);choice.setTextColor(ink);choice.setChecked(preferences.getBoolean(key,!key.equals("include_terrain")));sync.addView(choice);
            choice.setOnCheckedChangeListener((v,checked)->{preferences.edit().putBoolean(key,checked).apply();profileDirty=true;});
        }
        addText(sync,"The first recovery sync downloads each day in your selected range. Later syncs reuse history. Sign-out clears saved health and activity data.",12,muted,false,10);
        button(sync,"Classification: "+setting("classification_mode","web")+" ▾",false,()->chooseMode("Automatic categories","classification_mode",new String[]{"Web rules (including injury / rebuild dates)","Original Android title / HR suggestions"},new String[]{"web","native"}));
        EditText maximum=input(sync,"Maximum heart rate (intensity normalization)",InputType.TYPE_CLASS_NUMBER);maximum.setText(Integer.toString(preferences.getInt("max_hr",191)));
        button(sync,"Save maximum HR",false,()->{try{int hr=Integer.parseInt(maximum.getText().toString());if(hr<80||hr>240)throw new NumberFormatException();preferences.edit().putInt("max_hr",hr).apply();profileDirty=true;message.setText("Maximum HR saved.");}catch(NumberFormatException e){maximum.setError("Use 80–240 bpm");}});
        LinearLayout heart=card();addText(heart,"Easy-run heart rate",19,ink,true,0);
        EditText target=input(heart,"Suggest easy when average HR is below (bpm)",InputType.TYPE_CLASS_NUMBER);
        target.setText(Integer.toString(preferences.getInt("easy_hr",134)));
        button(heart,"Save HR target",false,()-> {
            try{
                int hr=Integer.parseInt(target.getText().toString());if(hr<40||hr>240){target.setError("Use 40–240 bpm");return;}
                preferences.edit().putInt("easy_hr",hr).apply();profileDirty=true;target.clearFocus();
                ((android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(target.getWindowToken(),0);
                message.setText("Target saved: below "+hr+" bpm.");
            }catch(NumberFormatException invalid){target.setError("Enter a number in bpm");}
        });
        addText(heart,"A low average can include higher peaks. Interval and trial titles take priority. You can correct any category in Runs.",12,muted,false,12);
    }
    private void renderRuns(JSONObject data) {
        if(data!=null)dashboardData=data;
        if(screen==2){renderProfile();return;}
        profileOpen=false;content.removeAllViews();updateChrome();
        if(dashboardData==null){addText(content,"Your charts will appear after the first download.",16,muted,false,20);return;}
        if(screen==1)renderSessions();else renderTrends();
    }
    private String setting(String key,String fallback){try{return settings().optString(key,fallback);}catch(Exception e){return fallback;}}
    private void saveSetting(String key,Object value){
        try{JSONObject state=settings();state.put(key,value);preferences.edit().putString("settings",state.toString()).apply();}
        catch(Exception e){message.setText("Could not save the setting.");}
    }
    private void chooseMode(String title,String key,String[] labels,String[] values){
        String current=setting(key,values[0]);int selected=0;
        for(int i=0;i<values.length;i++)if(current.equals(values[i]))selected=i;
        new AlertDialog.Builder(this).setTitle(title).setSingleChoiceItems(labels,selected,(dialog,which)->{
            saveSetting(key,values[which]);dialog.dismiss();loadDashboard(false);
        }).setNegativeButton("Cancel",null).show();
    }
    private void chooseDates(){
        LocalDate end=LocalDate.now(),start=end.minusDays(89);
        try{start=LocalDate.parse(setting("custom_start",start.toString()));}catch(Exception ignored){}
        final LocalDate first=start;
        android.app.DatePickerDialog picker=new android.app.DatePickerDialog(this,(view,y,m,d)->{
            final LocalDate selectedStart=LocalDate.of(y,m+1,d);
            android.app.DatePickerDialog finish=new android.app.DatePickerDialog(this,(v,yy,mm,dd)->{
                LocalDate selectedEnd=LocalDate.of(yy,mm+1,dd);
                if(selectedStart.isAfter(selectedEnd)){message.setText("Start must be before the end date.");return;}
                saveSetting("custom_start",selectedStart.toString());saveSetting("custom_end",selectedEnd.toString());
                days=-1;preferences.edit().putInt("days",days).apply();updateChrome();loadDashboard(false);
            },end.getYear(),end.getMonthValue()-1,end.getDayOfMonth());
            finish.setTitle("End date");finish.getDatePicker().setMaxDate(System.currentTimeMillis());finish.show();
        },first.getYear(),first.getMonthValue()-1,first.getDayOfMonth());
        picker.setTitle("Start date");picker.getDatePicker().setMaxDate(System.currentTimeMillis());picker.show();
    }
    private void paceMode(LinearLayout panel,String key){
        button(panel,"intensity".equals(setting(key,"observed"))?"Intensity normalized ▾":"Observed pace ▾",false,()->
            chooseMode("Pace mode",key,new String[]{"Observed","Intensity normalized (requires HR + resting HR)"},new String[]{"observed","intensity"}));
    }
    private void renderTrends() {
        JSONObject data=dashboardData,summary=data.optJSONObject("summary");
        addText(content,data.optString("start")+" – "+data.optString("end"),11,muted,false,0);
        if(summary!=null)renderKpis(summary);
        addText(content,"Elevation / temp adjustments apply wherever source measurements are available.",12,muted,false,4);
        int attention=countAttention();if(attention>0)button(attention+" sessions need review  →",false,()->{runFilter="attention";selectScreen(1);});
        weeklyCard();
        boolean average="session".equals(setting("interval_mode","session"));
        chartCard("Interval Pace",average?"Average pace of work intervals":"One dot per work interval",data.optJSONArray("interval_points"),false,new String[]{"short","medium","long"});
        LinearLayout prediction=card();addText(prediction,"5K Time Trials",20,ink,true,0);paceMode(prediction,"prediction_mode");
        JSONArray trials=new JSONArray();
        for(String key:new String[]{"trial_points","prediction_points","easy_prediction_points"}){
            if(!preferences.getBoolean("show_"+key,true))continue;
            JSONArray series=data.optJSONArray(key);if(series!=null)for(int i=0;i<series.length();i++)trials.put(series.optJSONObject(i));
        }
        String[] seriesKeys={"trial_points","prediction_points","easy_prediction_points"};
        String[] seriesNames={"Measured TT","Interval estimate","Outdoor easy estimate"};
        String[] seriesColors={"trial","prediction","easy_prediction"};
        for(int i=0;i<seriesKeys.length;i++){
            final String key=seriesKeys[i];CheckBox choice=new CheckBox(this);choice.setText(seriesNames[i]);choice.setTextColor(ScatterPlot.color(seriesColors[i]));choice.setChecked(preferences.getBoolean("show_"+key,true));prediction.addView(choice);
            choice.setOnCheckedChangeListener((view,checked)->{if(!busy){preferences.edit().putBoolean("show_"+key,checked).apply();renderRuns(null);}});
        }
        addText(prediction,"Easy estimates require at least two trial calibrations. Estimates describe trends, not measured race results.",12,muted,false,8);
        addPlot(prediction,trials,null,null,Double.NaN,true);
        chartCard("Easy Pace","Whole-run pace · HR target < "+preferences.getInt("easy_hr",134)+" bpm",data.optJSONArray("run_points"),false,new String[]{"easy"});
        LinearLayout hr=card();addText(hr,"Easy HR Control",20,ink,true,0);
        addText(hr,"Average HR against your ceiling. Colour shows recorded time below it: green ≥90%, orange ≥75%, red <75%.",12,muted,false,6);
        addPlot(hr,data.optJSONArray("hr_points"),"value","AVERAGE HR · BPM",preferences.getInt("easy_hr",134),false);
        renderTargets();recoveryCard();recentSessions();
        JSONArray warnings=data.optJSONArray("warnings");if(warnings!=null)for(int i=0;i<warnings.length();i++)addText(content,warnings.optString(i),13,muted,false,8);
        if(data.optInt("split_failures")>0)addText(content,"Some lap downloads failed. Tap Refresh to retry.",13,muted,false,8);
    }
    private void addPlot(LinearLayout panel,JSONArray points,String key,String label,double reference,boolean trial){
        if(points==null||points.length()==0){addText(panel,"No matching measurements in this range.",14,muted,false,16);return;}
        String start=dashboardData.optString("start");
        if(key!=null)start=LocalDate.parse(start).minusDays(6).toString();
        ScatterPlot plot=new ScatterPlot(this,points,start,dashboardData.optString("end"),miles,trial,false,key,label,reference,point->{
            if(key==null||point.has("id")){openRun(point);return;}
            new AlertDialog.Builder(this).setTitle(point.optString("date")).setMessage(label+"\n"+String.format(Locale.getDefault(),"%.2f",point.optDouble(key))).setPositiveButton("Close",null).show();
        });
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,dp(220));lp.topMargin=dp(12);panel.addView(plot,lp);
        plotActions(panel,plot::resetZoom,()->applyChartRange(plot.visibleDates()));
    }
    private void plotActions(LinearLayout panel,Runnable reset,Runnable filter){
        LinearLayout row=new LinearLayout(this);
        Button resetButton=actionButton("Reset chart",false,reset),filterButton=actionButton("Filter to visible dates",false,filter);
        LinearLayout.LayoutParams first=new LinearLayout.LayoutParams(0,dp(48),1);first.rightMargin=dp(6);row.addView(resetButton,first);row.addView(filterButton,new LinearLayout.LayoutParams(0,dp(48),1));
        LinearLayout.LayoutParams layout=new LinearLayout.LayoutParams(-1,-2);layout.topMargin=dp(8);panel.addView(row,layout);
    }
    private void applyChartRange(String[] range){
        saveSetting("custom_start",range[0]);saveSetting("custom_end",range[1]);days=-1;preferences.edit().putInt("days",days).apply();updateChrome();loadDashboard(false);
    }
    private void weeklyCard(){
        LinearLayout panel=card();addText(panel,"Weekly Load",20,ink,true,0);
        String[] keys={"training_load","total_minutes","run_minutes","interval_percent","run_miles"};
        String[] labels={"TRIMP load","Total time (hours)","Run time (hours)","Active interval %",miles?"Run miles":"Run kilometres"};
        String current=setting("weekly_metric","training_load");int selected=0;for(int i=0;i<keys.length;i++)if(keys[i].equals(current))selected=i;
        final String metric=keys[selected],label=labels[selected];
        button(panel,label+" ▾",false,()->chooseMode("Weekly metric","weekly_metric",labels,keys));
        JSONArray points=new JSONArray(),weeks=dashboardData.optJSONArray("weeks");
        if(weeks!=null)for(int i=0;i<weeks.length();i++){
            JSONObject week=weeks.optJSONObject(i);
            double value=week.optDouble(metric,0);if(metric.endsWith("minutes"))value/=60;if(metric.equals("run_miles")&&!miles)value*=1.609344;
            try{points.put(new JSONObject().put("date",week.optString("date")).put("value",value).put("bar",true).put("color",metric.equals("training_load")?Color.rgb(179,78,78):metric.equals("total_minutes")?Color.rgb(63,111,168):metric.equals("interval_percent")?Color.rgb(114,92,168):Color.rgb(40,124,113)));}catch(Exception ignored){}
        }
        addText(panel,"Calendar week totals · injury / rebuild period shaded",12,muted,false,6);
        addPlot(panel,points,"value",label.toUpperCase(Locale.ROOT),Double.NaN,false);
    }
    private void recoveryCard(){
        LinearLayout panel=card();addText(panel,"Weekly Recovery",20,ink,true,0);
        addText(panel,"Average sleep hours, resting HR, and overnight HRV",12,muted,false,6);
        JSONArray weeks=dashboardData.optJSONArray("weeks");if(weeks==null||weeks.length()==0){addText(panel,"No weekly recovery data.",14,muted,false,16);return;}
        RecoveryPlot plot=new RecoveryPlot(this,weeks,point->new AlertDialog.Builder(this).setTitle(point.optString("date"))
            .setMessage(point.optString("label")+": "+point.optString("formatted")+"\n"+point.optInt("days")+" measured days").setPositiveButton("Close",null).show());
        panel.addView(plot,new LinearLayout.LayoutParams(-1,dp(330)));plotActions(panel,plot::resetZoom,()->applyChartRange(plot.visibleDates()));
    }
    private void renderKpis(JSONObject summary){
        JSONObject best=summary.optJSONObject("best_trial"),latest=summary.optJSONObject("latest_trial");
        String distance=miles?"mi":"km";double multiplier=miles?1:1.609344;
        String[] labels={"Run volume","Easy HR discipline","Best 5K trial","Latest 5K trial","Intervals","Cross-training"};
        String[] values={String.format(Locale.getDefault(),"%.1f %s",summary.optDouble("run_miles")*multiplier,distance),summary.isNull("easy_percent")?"—":Math.round(summary.optDouble("easy_percent"))+"%",
            best==null?"—":raceTime(best.optJSONObject("best_5k").optDouble("duration")),latest==null?"—":raceTime(latest.optJSONObject("best_5k").optDouble("duration")),Integer.toString(summary.optInt("interval_count")),String.format(Locale.getDefault(),"%.1f h",summary.optDouble("cross_hours"))};
        String[] notes={String.format(Locale.getDefault(),"%.1f %s/wk · last 4 weeks",summary.optDouble("last_four_miles",0)*multiplier,distance),"time below "+preferences.getInt("easy_hr",134)+" bpm",best==null?"no trials in range":best.optString("date"),latest==null?"no trials in range":latest.optString("date"),"short, medium & long sessions","cycling, elliptical, swim & rides"};
        for(int row=0;row<3;row++){
            LinearLayout tiles=new LinearLayout(this);LinearLayout.LayoutParams rowParams=new LinearLayout.LayoutParams(-1,-2);rowParams.bottomMargin=dp(8);content.addView(tiles,rowParams);
            for(int column=0;column<2;column++){
                int i=row*2+column;LinearLayout tile=new LinearLayout(this);tile.setOrientation(LinearLayout.VERTICAL);tile.setPadding(dp(12),dp(12),dp(12),dp(12));tile.setBackground(panelShape());
                addText(tile,labels[i],11,muted,true,0);addText(tile,values[i],25,ink,true,8);addText(tile,notes[i],10,muted,false,6);
                LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,-1,1);if(column==0)lp.rightMargin=dp(8);tiles.addView(tile,lp);
            }
        }
    }
    private void recentSessions(){
        LinearLayout panel=card();addText(panel,"Recent Sessions",20,ink,true,0);addText(panel,"Latest activities in the selected range",12,muted,false,4);
        String[] keys={"all","easy","easy_long","short","medium","long","trial","warmup","rebuild_run","cross_train","cross_interval","strength","other_run","other"};
        String[] labels=new String[keys.length];labels[0]="All types";for(int i=1;i<keys.length;i++)labels[i]=ScatterPlot.label(keys[i]);
        String filter=setting("recent_filter","all");button(panel,(filter.equals("all")?"All types":ScatterPlot.label(filter))+" ▾",false,()->chooseMode("Session type","recent_filter",labels,keys));
        JSONArray rows=dashboardData.optJSONArray("runs");int shown=0;
        if(rows!=null)for(int i=0;i<rows.length()&&shown<10;i++){
            JSONObject run=rows.optJSONObject(i);if(!filter.equals("all")&&!filter.equals(run.optString("category")))continue;shown++;
            LinearLayout item=new LinearLayout(this);item.setOrientation(LinearLayout.VERTICAL);item.setPadding(0,dp(14),0,dp(14));
            addText(item,run.optString("date")+" · "+ScatterPlot.label(run.optString("category")),11,ScatterPlot.color(run.optString("category")),true,0);
            addText(item,run.optString("title"),15,ink,true,5);addText(item,sessionMetrics(run),12,muted,false,5);
            item.setOnClickListener(v->{if(!busy)showRun(run);});panel.addView(item,new LinearLayout.LayoutParams(-1,-2));
            View divider=new View(this);divider.setBackgroundColor(Color.rgb(223,228,220));panel.addView(divider,new LinearLayout.LayoutParams(-1,dp(1)));
        }
        if(shown==0)addText(panel,"No sessions of this type.",14,muted,false,14);
        button(panel,"All sessions →",false,()->{runFilter=filter;selectScreen(1);});
    }
    private String sessionMetrics(JSONObject run){
        String info=displayPace(run)+" · "+distanceText(run);
        double hr=run.optDouble("work_hr",run.optDouble("average_hr",Double.NaN));if(Double.isFinite(hr))info+=" · "+Math.round(hr)+" bpm";
        if(!run.isNull("hr_under_percent"))info+="\nEasy HR "+Math.round(run.optDouble("hr_under_percent"))+"% below ceiling";
        if(!run.isNull("elevation_gain"))info+=" · +"+Math.round(run.optDouble("elevation_gain")*3.28084)+" ft";
        JSONObject weather=run.optJSONObject("weather");if(weather!=null&&!weather.isNull("temperatureF"))info+=" · "+Math.round(weather.optDouble("temperatureF"))+" °F";
        return info;
    }
    private String displayPace(JSONObject run){return run.isNull("display_pace")?paceText(run):ScatterPlot.pace(run.optDouble("display_pace"),miles)+(miles?" /mi":" /km");}
    private void renderTargets(){
        LinearLayout panel=card();addText(panel,"Interval Targets",20,ink,true,0);
        String source=setting("target_source","predicted");
        button(panel,"5K source: "+source+" ▾",false,()->chooseMode("5K target source","target_source",new String[]{"Predicted","Latest measured TT","Custom time"},new String[]{"predicted","latest","custom"}));
        button(panel,"Edit time & conditions",false,this::editTargetConditions);
        JSONObject targets=dashboardData.optJSONObject("targets");if(targets==null)return;
        if(targets.has("error")){addText(panel,targets.optString("error"),14,muted,false,12);return;}
        addText(panel,"5K basis: "+ScatterPlot.pace(targets.optDouble("seconds"),false)+String.format(Locale.getDefault()," · FVDOT %.1f",targets.optDouble("vdot")),14,ink,true,12);
        addText(panel,"Conditions: "+setting("target_temperature","45")+" °F · gain "+setting("target_gain","0")+" ft · loss "+setting("target_loss","0")+" ft",12,muted,false,6);
        JSONArray rows=targets.optJSONArray("rows");if(rows!=null)for(int i=0;i<rows.length();i++){
            JSONObject row=rows.optJSONObject(i);addText(panel,ScatterPlot.label(row.optString("category"))+" · "+row.optString("reps"),14,ink,true,16);
            addText(panel,ScatterPlot.pace(row.optDouble("pace"),miles)+(miles?" /mi":" /km"),24,ink,true,4);
            addText(panel,"Base "+ScatterPlot.pace(row.optDouble("base_pace"),miles)+" · condition change "+String.format(Locale.getDefault(),"%+.0f s/%s",row.optDouble("delta")*(miles?1.609344:1),miles?"mi":"km"),12,muted,false,4);
        }
        addText(panel,"Elevation uses the latest matching interval distance, then whole-workout distance. It is skipped when neither is available.",12,muted,false,12);
        addText(panel,"Equivalent race times",18,ink,true,20);
        JSONArray races=targets.optJSONArray("races");if(races!=null)for(int i=0;i<races.length();i++){
            JSONObject row=races.optJSONObject(i);addText(panel,row.optString("label")+"   "+raceTime(row.optDouble("duration"))+" · "+ScatterPlot.pace(row.optDouble("pace"),miles)+(miles?" /mi":" /km"),14,ink,false,10);
            if(Math.abs(row.optDouble("duration")-row.optDouble("base_duration"))>=.5)addText(panel,"Base "+raceTime(row.optDouble("base_duration"))+" · change "+String.format(Locale.getDefault(),"%+.0f s",row.optDouble("duration")-row.optDouble("base_duration")),11,muted,false,3);
        }
    }
    private String raceTime(double value){long seconds=Math.round(value);return seconds>=3600?String.format(Locale.getDefault(),"%d:%02d:%02d",seconds/3600,seconds/60%60,seconds%60):ScatterPlot.pace(value,false);}
    private void editTargetConditions(){
        LinearLayout form=new LinearLayout(this);form.setOrientation(LinearLayout.VERTICAL);form.setPadding(dp(20),0,dp(20),dp(20));
        String[] keys={"target_time","target_temperature","target_humidity","target_gain","target_loss","race_distance_miles"};
        String[] labels={"Custom 5K time (mm:ss)","Temperature °F","Humidity % (optional)","Elevation gain ft","Elevation loss ft","Extra race distance miles (optional)"};
        String[] defaults={"","45","","0","0",""};EditText[] fields=new EditText[keys.length];
        for(int i=0;i<keys.length;i++){
            fields[i]=input(form,labels[i],i==0?InputType.TYPE_CLASS_TEXT:InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_DECIMAL|InputType.TYPE_NUMBER_FLAG_SIGNED);
            fields[i].setText(setting(keys[i],defaults[i]));
        }
        ScrollView wrapper=new ScrollView(this);wrapper.addView(form);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("Target time & conditions").setView(wrapper).setPositiveButton("Save",null).setNegativeButton("Cancel",null).create();
        dialog.setOnShowListener(d->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{
            for(int i=1;i<fields.length;i++){
                String value=fields[i].getText().toString().trim();if(value.isEmpty())continue;
                try{double n=Double.parseDouble(value);if(!Double.isFinite(n)||(i==2&&(n<0||n>100))||(i>=3&&n<0)||(i==5&&(n<=0||n>200)))throw new NumberFormatException();}
                catch(NumberFormatException e){fields[i].setError("Enter a valid value");return;}
            }
            for(int i=0;i<keys.length;i++)saveSetting(keys[i],fields[i].getText().toString().trim());
            dialog.dismiss();loadDashboard(false);
        }));dialog.show();
    }
    private void chartCard(String title,String subtitle,JSONArray points,boolean trial,String[] categories) {
        LinearLayout panel=card();if(points==null)points=new JSONArray();
        boolean easy=categories.length==1&&"easy".equals(categories[0]);
        boolean fixedEasy=easy&&!preferences.getBoolean("easy_auto_scale",false);
        LinearLayout titleRow=new LinearLayout(this);titleRow.setGravity(android.view.Gravity.CENTER_VERTICAL);
        titleRow.addView(text(title,20,ink,true),new LinearLayout.LayoutParams(0,-2,1));
        if(easy){
            Button scale=actionButton("Scale ▾",false,()->new AlertDialog.Builder(this).setTitle("Easy-run pace scale")
                .setSingleChoiceItems(new String[]{"7:00–10:00 min/mile (web default)","Fit to data"},preferences.getBoolean("easy_auto_scale",false)?1:0,(dialog,which)->{
                    preferences.edit().putBoolean("easy_auto_scale",which==1).apply();dialog.dismiss();renderRuns(null);
                }).setNegativeButton("Cancel",null).show());
            scale.setTextSize(12);titleRow.addView(scale,new LinearLayout.LayoutParams(dp(84),dp(48)));
        }
        panel.addView(titleRow);addText(panel,subtitle,12,muted,false,4);
        paceMode(panel,easy?"easy_mode":"interval_pace_mode");
        if(easy)addText(panel,"● Road / treadmill   ▲ Trail · shaded rolling 25–75% range",11,muted,false,8);
        if(points.length()>0){
            if(categories.length>1){
                LinearLayout legend=new LinearLayout(this);
                for(String category:categories){
                    String label=category.substring(0,1).toUpperCase(Locale.getDefault())+category.substring(1);
                    TextView item=text("● "+label,12,ScatterPlot.color(category),true);legend.addView(item,new LinearLayout.LayoutParams(0,-2,1));
                }
                LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(12);panel.addView(legend,lp);
            }
            ScatterPlot plot=new ScatterPlot(this,points,dashboardData.optString("start"),dashboardData.optString("end"),miles,trial,fixedEasy,this::openRun);
            LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,dp(210));lp.topMargin=dp(12);panel.addView(plot,lp);
            LinearLayout controls=new LinearLayout(this);controls.setGravity(android.view.Gravity.CENTER_VERTICAL);
            controls.addView(text("Pinch to zoom · drag when zoomed",11,muted,false),new LinearLayout.LayoutParams(0,-2,1));
            Button reset=actionButton("Reset",false,plot::resetZoom);reset.setTextSize(12);controls.addView(reset,new LinearLayout.LayoutParams(dp(64),dp(48)));
            Button filter=actionButton("Filter dates",false,()->applyChartRange(plot.visibleDates()));filter.setTextSize(11);LinearLayout.LayoutParams filterParams=new LinearLayout.LayoutParams(dp(86),dp(48));filterParams.leftMargin=dp(6);controls.addView(filter,filterParams);panel.addView(controls);
            if(fixedEasy){
                int outside=0;for(int i=0;i<points.length();i++){
                    double pace=points.optJSONObject(i).optDouble("pace",Double.NaN)*1.609344;
                    if(pace<420||pace>600)outside++;
                }
                if(outside>0)addText(panel,outside+" runs outside this scale · choose Fit to data to view",12,muted,false,2);
            }
            addText(panel,points.length()+(trial?" recorded trials":categories.length>1?" interval points":" easy runs")+" · Faster is higher",11,muted,false,0);
        }else{
            addText(panel,trial?"No usable 5K recordings in this range.":"No matching runs in this range.",15,muted,false,20);
            if(trial&&days<365){
                Button year=actionButton("Look in the last year",false,()->changeRange(365));
                LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,dp(48));lp.topMargin=dp(12);panel.addView(year,lp);
            }else addText(panel,trial?"Find your trial in Runs and set its category to 5K time trial.":"Open Runs to check categories or select work laps.",12,muted,false,8);
        }
    }
    private boolean needsReview(JSONObject run) {
        if(run==null)return false;
        String kind=run.optString("category");if("other".equals(kind))return run.optBoolean("is_run",true);
        if(kind.equals("short")||kind.equals("medium")||kind.equals("long"))return run.optInt("work_reps")==0;
        if(kind.equals("trial")){
            JSONArray points=dashboardData.optJSONArray("trial_points");
            if(points!=null)for(int i=0;i<points.length();i++)if(run.optString("id").equals(points.optJSONObject(i).optString("id")))return false;
            return true;
        }
        return false;
    }
    private int countAttention(){
        int count=0;JSONArray rows=dashboardData.optJSONArray("runs");
        if(rows!=null)for(int i=0;i<rows.length();i++)if(needsReview(rows.optJSONObject(i)))count++;
        return count;
    }
    private void renderSessions() {
        addText(content,dashboardData.optString("start")+" – "+dashboardData.optString("end"),11,muted,false,0);
        EditText search=new EditText(this);search.setSingleLine(true);search.setTextSize(15);search.setTextColor(ink);
        search.setHint("Search session titles");search.setHintTextColor(muted);search.setPadding(dp(14),0,dp(14),0);search.setBackground(shape(Color.WHITE,12));
        search.setInputType(InputType.TYPE_CLASS_TEXT);search.setText(query);content.addView(search,new LinearLayout.LayoutParams(-1,dp(48)));
        HorizontalScrollView filters=new HorizontalScrollView(this);filters.setHorizontalScrollBarEnabled(false);
        LinearLayout chips=new LinearLayout(this);String[] keys={"all","attention","easy","easy_long","short","medium","long","trial","cross_train","cross_interval","strength","warmup","rebuild_run","other_run","other"};
        String[] labels={"All","Needs review","Easy","Easy Long","Short","Medium","Long","5K","Cross-training","Cross intervals","Strength","Warmup","Rebuild","Other run","Other"};int selected=0;
        for(int i=0;i<keys.length;i++){
            final String key=keys[i];if(key.equals(runFilter))selected=i;
            Button chip=actionButton(labels[i],key.equals(runFilter),()->{runFilter=key;visibleRuns=30;renderRuns(null);});chip.setTextSize(12);
            LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-2,dp(48));lp.rightMargin=dp(6);chips.addView(chip,lp);
        }
        filters.addView(chips);LinearLayout.LayoutParams fl=new LinearLayout.LayoutParams(-1,-2);fl.topMargin=dp(10);content.addView(filters,fl);
        final int selectedFilter=selected;filters.post(()->filters.smoothScrollTo(chips.getChildAt(selectedFilter).getLeft(),0));
        runList=new LinearLayout(this);runList.setOrientation(LinearLayout.VERTICAL);content.addView(runList);renderRunList();
        search.addTextChangedListener(new TextWatcher(){
            public void beforeTextChanged(CharSequence v,int start,int count,int after){}
            public void onTextChanged(CharSequence v,int start,int before,int count){query=v.toString();visibleRuns=30;renderRunList();}
            public void afterTextChanged(Editable value){}
        });
    }
    private void renderRunList() {
        runList.removeAllViews();JSONArray runs=dashboardData.optJSONArray("runs");int matching=0;
        if(runs!=null)for(int i=0;i<runs.length();i++){
            JSONObject run=runs.optJSONObject(i);if(run==null)continue;
            if(!run.optString("title").toLowerCase(Locale.ROOT).contains(query.toLowerCase(Locale.ROOT)))continue;
            if("attention".equals(runFilter)?!needsReview(run):!"all".equals(runFilter)&&!runFilter.equals(run.optString("category")))continue;
            matching++;if(matching>visibleRuns)continue;
            LinearLayout row=new LinearLayout(this);row.setOrientation(LinearLayout.VERTICAL);row.setPadding(dp(16),dp(14),dp(16),dp(14));
            row.setBackground(shape(Color.WHITE,14));row.setMinimumHeight(dp(108));row.setFocusable(true);
            String category=run.optString("category");
            addText(row,run.optString("date")+" · "+ScatterPlot.label(category),11,ScatterPlot.color(category),true,0);
            TextView title=addText(row,run.optString("title"),16,ink,true,6);title.setMaxLines(2);title.setEllipsize(TextUtils.TruncateAt.END);
            String info=sessionMetrics(run);
            if(run.has("best_5k"))info="Best 5K "+ScatterPlot.pace(run.optJSONObject("best_5k").optDouble("duration"),false)+" · "+info;
            addText(row,info,12,muted,false,6);
            if(needsReview(run))addText(row,category.equals("other")?"Choose a category  →":category.equals("trial")?"Check 5K recording  →":"Check work laps  →",12,muted,false,8);
            row.setContentDescription(run.optString("title")+", "+run.optString("date")+", "+ScatterPlot.label(category)+", "+info+". Open run details.");
            row.setOnClickListener(v->{if(!busy)showRun(run);});
            LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(10);runList.addView(row,lp);
        }
        if(matching==0)addText(runList,"No runs match. Try another filter or date range.",15,muted,false,24);
        else{
            addText(runList,matching+" matching runs",12,muted,false,12);
            if(matching>visibleRuns){Button more=actionButton("Show more runs",false,()->{visibleRuns+=30;renderRunList();});LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,dp(48));lp.topMargin=dp(12);runList.addView(more,lp);}
        }
    }
    private String paceText(JSONObject run){return run.isNull("pace")?"Pace unavailable":ScatterPlot.pace(run.optDouble("pace"),miles)+(miles?" /mi":" /km");}
    private String distanceText(JSONObject run){return run.isNull("distance")?"Distance unavailable":String.format(Locale.getDefault(),"%.2f %s",run.optDouble("distance")/(miles?1609.344:1000),miles?"mi":"km");}
    private void openRun(JSONObject point) {
        String identity=point.optString("id");
        if(busy||dashboardData==null)return;JSONArray runs=dashboardData.optJSONArray("runs");
        if(runs!=null)for(int i=0;i<runs.length();i++)if(identity.equals(runs.optJSONObject(i).optString("id"))){showRun(runs.optJSONObject(i),point);return;}
    }
    private void showRun(JSONObject run) {showRun(run,null);}
    private void showRun(JSONObject run,JSONObject point) {
        String detail=run.optString("date")+"\n"+ScatterPlot.label(run.optString("category"))+"\n\n"+paceText(run)+" · "+distanceText(run);
        if(point!=null&&("prediction".equals(point.optString("category"))||"easy_prediction".equals(point.optString("category")))){
            detail+="\n\nEstimated 5K: "+raceTime(point.optDouble("duration"))+"\nCalibrated from "+point.optInt("calibrations")+" trials";
        }
        if(point!=null&&point.has("lap")){
            detail+="\n\nSelected dot: "+paceText(point);
            if(point.optInt("lap")>0)detail+="\nWork lap "+point.optInt("lap")+(point.has("last_lap")?"–"+point.optInt("last_lap"):"");
            if(point.optInt("reps")>0)detail+="\nAverage of "+point.optInt("reps")+" work intervals";
        }
        if(!run.isNull("duration"))detail+="\nWhole activity timer: "+ScatterPlot.pace(run.optDouble("duration"),false);
        if(!run.isNull("average_hr")){
            detail+="\n\nAverage HR: "+Math.round(run.optDouble("average_hr"))+" bpm";
            if(!run.isNull("max_hr"))detail+="\nPeak HR: "+Math.round(run.optDouble("max_hr"))+" bpm";
            detail+="\nAverage "+(run.optBoolean("hr_below_target")?"below":"at/above")+" your "+run.optInt("hr_target",134)+" bpm target";
        }
        if("average_hr".equals(run.optString("category_reason")))detail+="\nSuggested easy from average HR; peaks may be higher.";
        if(run.has("hr_under_percent"))detail+="\nTime under HR ceiling: "+Math.round(run.optDouble("hr_under_percent"))+"% ("+run.optString("hr_source")+")";
        if(run.has("work_reps"))detail+="\n\n"+run.optInt("work_reps")+" work intervals identified";
        JSONObject effort=run.optJSONObject("best_5k");
        if(effort!=null){
            detail+="\n\nFastest continuous 5 km: "+ScatterPlot.pace(effort.optDouble("duration"),false);
            if(effort.has("start_distance"))detail+=String.format(Locale.getDefault(),"\nSegment: %.2f–%.2f km into the activity",effort.optDouble("start_distance")/1000,effort.optDouble("end_distance")/1000);
            detail+="garmin_fastest_split".equals(effort.optString("method"))?"\nGarmin recorded fastest 5K split; segment boundaries unavailable.":"\nElapsed time, including pauses. Boundaries interpolated between recorded samples.";
        }
        if(run.has("training_load")&&!run.isNull("training_load"))detail+="\nTraining load: "+Math.round(run.optDouble("training_load"));
        JSONObject weather=run.optJSONObject("weather");if(weather!=null&&!weather.isNull("temperatureF"))detail+="\nWeather: "+Math.round(weather.optDouble("temperatureF"))+" °F ("+weather.optString("source","Garmin")+")";
        if(weather!=null&&!weather.isNull("humidity"))detail+="\nHumidity: "+Math.round(weather.optDouble("humidity"))+"%";
        if(weather!=null&&!weather.isNull("observation_time"))detail+="\nStation observation: "+weather.optString("observation_time")+" ("+Math.round(weather.optDouble("observation_offset"))+" min from midpoint)";
        if(!run.isNull("work_hr"))detail+="\nWork interval HR: "+Math.round(run.optDouble("work_hr"))+" bpm";
        if(run.has("work_source"))detail+="\nWork metrics: "+run.optString("work_source");
        if(!run.isNull("elevation_gain"))detail+="\nElevation gain: "+Math.round(run.optDouble("elevation_gain")*3.28084)+" ft ("+run.optString("elevation_source","Garmin")+")";
        if(run.has("trial_error"))detail+="\n\n"+run.optString("trial_error");
        String category=run.optString("category");
        AlertDialog.Builder dialog=new AlertDialog.Builder(this).setTitle(run.optString("title")).setMessage(detail)
            .setNegativeButton("Close",null).setNeutralButton("Category",(d,w)->chooseCategory(run));
        if(category.equals("short")||category.equals("medium")||category.equals("long"))dialog.setPositiveButton("Work laps",(d,w)->chooseLaps(run));
        dialog.show();
    }
    private void chooseCategory(JSONObject run) {
        new AlertDialog.Builder(this).setTitle(run.optString("title")).setSingleChoiceItems(ScatterPlot.LABELS,ScatterPlot.index(run.optString("category")),(dialog,which)-> {
            try {
                JSONObject state=settings(),categories=state.optJSONObject("categories");if(categories==null)categories=new JSONObject();
                categories.put(run.optString("id"),ScatterPlot.KEYS[which]);state.put("categories",categories);
                preferences.edit().putString("settings",state.toString()).apply();dialog.dismiss();loadDashboard(false);
            }catch(Exception ignored){}
        }).setNeutralButton("Use automatic",(dialog,which)->{
            try{JSONObject state=settings(),categories=state.optJSONObject("categories");if(categories!=null)categories.remove(run.optString("id"));preferences.edit().putString("settings",state.toString()).apply();loadDashboard(false);}catch(Exception ignored){}
        }).setNegativeButton("Cancel",null).show();
    }
    private void chooseLaps(JSONObject run) {
        execute("Loading Garmin laps…",()->invoke("laps",run.optString("id")),data-> {
            JSONArray laps=data.optJSONArray("laps");if(laps==null||laps.length()==0){message.setText("Garmin has no laps for this session.");return;}
            String[] labels=new String[laps.length()];boolean[] selected=new boolean[laps.length()];
            JSONObject saved=null;try{saved=settings().optJSONObject("laps");}catch(Exception ignored){}
            JSONArray manual=saved==null?null:saved.optJSONArray(run.optString("id"));
            for(int i=0;i<laps.length();i++) {
                JSONObject lap=laps.optJSONObject(i);if(lap==null)continue;
                String intensity=lap.optString("intensity");
                selected[i]=manual==null&&(intensity.equals("ACTIVE")||intensity.equals("INTERVAL")||intensity.equals("WORK")||intensity.equals("WORK_INTERVAL"));
                if(manual!=null)for(int j=0;j<manual.length();j++)if(manual.optInt(j,-1)==i)selected[i]=true;
                labels[i]="Lap "+(i+1)+" · "+Math.round(lap.optDouble("distance",0))+" m · "+
                    (lap.isNull("pace")?"No pace":ScatterPlot.pace(lap.optDouble("pace"),miles)) + (intensity.isEmpty()?"":" · "+intensity);
            }
            new AlertDialog.Builder(this).setTitle("Select work laps only").setMultiChoiceItems(labels,selected,(dialog,which,checked)->selected[which]=checked)
                .setPositiveButton("Save",(dialog,which)-> {
                    try {
                        JSONObject state=settings(),choices=state.optJSONObject("laps");if(choices==null)choices=new JSONObject();
                        JSONArray indices=new JSONArray();for(int i=0;i<selected.length;i++)if(selected[i])indices.put(i);
                        choices.put(run.optString("id"),indices);state.put("laps",choices);preferences.edit().putString("settings",state.toString()).apply();loadDashboard(false);
                    }catch(Exception ignored){}
                }).setNeutralButton("Use Garmin labels",(dialog,which)-> {
                    try{JSONObject state=settings(),choices=state.optJSONObject("laps");if(choices!=null)choices.remove(run.optString("id"));preferences.edit().putString("settings",state.toString()).apply();loadDashboard(false);}catch(Exception ignored){}
                }).setNegativeButton("Cancel",null).show();
        });
    }
    public final class DownloadProgress implements ProgressSink {
        public void update(String label,int completed,int total){runOnUiThread(()->{
            if(isDestroyed()||!busy)return;message.setText(label);recordProgress(label);
            downloadProgress.setIndeterminate(total<=0);
            if(total>0){downloadProgress.setMax(total);downloadProgress.setProgress(completed);}
        });}
    }
    private void loadRuns(){loadDashboard(true);}
    private void loadDashboard(boolean refresh) {
        execute(refresh?"Connecting to Garmin…":"Updating charts…",()->invoke("dashboard",LocalDate.now().toString(),days,settings().toString(),refresh,new DownloadProgress()),data->{profileDirty=false;renderRuns(data);message.setText("✓ Updated · "+data.optJSONArray("runs").length()+" sessions · "+java.time.LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))+(data.optJSONArray("warnings")!=null&&data.optJSONArray("warnings").length()>0?" · Some downloads need retry":""));});
    }
    private void handleSampleRequest() {
        if(pendingSample==null||busy||!authenticated)return;
        Uri uri=pendingSample;pendingSample=null;
        if(!"rundashboard".equals(uri.getScheme())||!"sample".equals(uri.getHost()))return;
        final int port;final String token=uri.getQueryParameter("token");
        try{port=Integer.parseInt(uri.getQueryParameter("port"));}catch(Exception invalid){return;}
        if(port<1024||port>65535||token==null||!token.matches("[A-Za-z0-9_-]{24,128}"))return;
        new AlertDialog.Builder(this).setTitle("Share a training sample?")
            .setMessage("Send up to 20 run titles from the last year (prioritizing labeled 5K trials), dates, paces, lap summaries and fastest 5K summaries to the local development project on this phone? Credentials, session tokens, location and heart rate are excluded.")
            .setPositiveButton("Share sample",(dialog,which)->execute("Preparing your training sample…",()-> {
                JSONObject result=invoke("sample",LocalDate.now().toString());
                if(!result.optBoolean("ok"))return result;
                byte[] body=result.getJSONObject("sample").toString().getBytes(StandardCharsets.UTF_8);
                HttpURLConnection conn=(HttpURLConnection)new URL("http://127.0.0.1:"+port+"/sample/"+token).openConnection();
                conn.setConnectTimeout(10000);conn.setReadTimeout(10000);conn.setInstanceFollowRedirects(false);
                try {
                    conn.setRequestMethod("POST");conn.setDoOutput(true);conn.setRequestProperty("Content-Type","application/json");
                    try(java.io.OutputStream out=conn.getOutputStream()){out.write(body);}
                    if(conn.getResponseCode()!=200)throw new Exception("Local receiver unavailable");
                }finally{conn.disconnect();}
                return result;
            },result->message.setText("Training sample shared with the local project.")))
            .setNegativeButton("Cancel",null).show();
    }
    private void logout() {
        execute("Signing out…",()->{store.clear();dashboardData=null;preferences.edit().remove("settings").apply();return invoke("logout");},result->{profileOpen=true;screen=2;render(result);message.setText("Signed out. Your saved session was removed.");});
    }
    private JSONObject invoke(String operation,Object... args) throws Exception {
        Object[] callArgs=new Object[args.length+1];callArgs[0]=operation;System.arraycopy(args,0,callArgs,1,args.length);
        JSONObject result=new JSONObject(backend.callAttr("call",callArgs).toString());
        if(result.optBoolean("ok") && result.optBoolean("authenticated") && !result.isNull("tokens")) store.save(result.getJSONObject("tokens"));
        return result;
    }
    private interface Work {JSONObject run() throws Exception;}
    private interface Result {void accept(JSONObject data);}
    private void enable(View view,boolean enabled) {
        view.setEnabled(enabled);
        if(view instanceof android.view.ViewGroup) {
            android.view.ViewGroup group=(android.view.ViewGroup)view;
            for(int i=0;i<group.getChildCount();i++)enable(group.getChildAt(i),enabled);
        }
    }
    private void execute(String status,Work work,Result done) {
        if(busy)return;busy=true;enable(content,false);updateChrome();
        if(refreshButton!=null)refreshButton.setText("Syncing…");
        downloadProgress.setVisibility(View.VISIBLE);downloadProgress.setIndeterminate(true);
        syncLog.setLength(0);recordProgress(status);
        message.setTextColor(muted);message.setText(status);
        WORKER.execute(()-> {
            JSONObject result=null;String error=null;
            try {result=work.run();} catch(Throwable failure) {error="Couldn't start or complete the request. Reopen the app and try again.";}
            final JSONObject data=result;final String failure=error;
            runOnUiThread(()-> {
                if(isDestroyed())return;
                busy=false;enable(content,true);updateChrome();downloadProgress.setVisibility(View.GONE);
                if(refreshButton!=null)refreshButton.setText("Refresh");
                if(failure!=null || data==null || !data.optBoolean("ok")) {
                    if(data!=null && !data.optBoolean("authenticated") && !authenticated) render(data);
                    recordProgress(failure!=null?failure:data==null?"Could not complete the request.":data.optString("error"));
                    message.setTextColor(Color.rgb(159,53,41));message.setText(failure!=null?failure:data==null?"Could not complete the request.":data.optString("error"));
                } else {recordProgress("Dashboard ready.");message.setText("");done.accept(data);}
                handleSampleRequest();
            });
        });
    }
}
