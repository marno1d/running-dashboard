package dev.rundashboard.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.Dialog;
import android.content.res.ColorStateList;
import android.graphics.drawable.Drawable;
import android.view.Gravity;
import android.view.ViewGroup;
import java.util.function.Consumer;
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
import java.time.LocalDate;
import android.text.Editable;
import android.text.TextWatcher;
import android.text.TextUtils;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import org.json.JSONObject;
import org.json.JSONArray;

public final class MainActivity extends Activity {
    private static final int TRENDS=0, SESSIONS=1, TARGETS=2, PROFILE=3, SCREEN_COUNT=4;
    private int ink,muted;
    private MaterialPalette palette;
    private LinearLayout statusBar;
    private View rangeArea;
    private Button pauseButton;
    private LinearLayout root, content, adjustBar, navigation, runList;
    private MaterialUi.ButtonGroup rangeBar;
    private final StringBuilder syncLog=new StringBuilder();
    private TextView logView;
    private TextView syncSheetStatus;
    private Button logButton;
    private ScrollView scroll;
    private PullRefreshLayout pullRefresh;
    private TextView heading;
    private final MaterialUi.NavigationItem[] tabs=new MaterialUi.NavigationItem[SCREEN_COUNT];
    private int screen=TARGETS, visibleRuns=30;
    private final int[] scrollPositions=new int[SCREEN_COUNT];
    private String runFilter="all", query="";
    private static final String[] SESSION_FILTER_KEYS={"all","short","medium","long","easy","easy_long","trial","cross_train","cross_interval","strength","warmup","rebuild_run","other_run","other","attention"};
    private static final String[] SESSION_FILTER_LABELS={"All","Short","Medium","Long","Easy","Easy Long","5K","Cross-training","Cross intervals","Strength","Warmup","Rebuild","Other run","Other","Needs review"};
    private TextView message;
    private SessionStore store;
    private boolean busy, authenticated, needsMfa, profileOpen, profileDirty;
    private Button refreshButton;
    private boolean syncRunning;
    private ProgressBar downloadProgress;
    private boolean backendReady, foreground, restoreScroll;
    private long seenSyncCompletion;
    private final SyncService.Listener syncListener=this::onSyncChanged;
    private JSONObject dashboardData;
    private android.content.SharedPreferences preferences;
    private int days;
    private boolean miles;
    private Uri pendingSample;
    private boolean syncDetailsOpen;
    private Dialog expandedChart,pointSheet;
    private final android.os.Handler conditionsHandler=new android.os.Handler(android.os.Looper.getMainLooper());
    private Runnable conditionsRefresh;
    private EditText[] conditionsFields;
    private TextView conditionsStatus;
    private LinearLayout targetPaces,targetPaceResults,equivalentRaceCard,raceRows;
    private EditText raceDistanceField;
    private TextView customRacePace,customRaceTime;
    private TextView workoutConditionsSummary;
    private TextView elevationMigrationNote;
    private final View[] elevationConditionColumns=new View[2];
    private Button manualElevationButton;
    private JSONArray savedTrainingRoutes=new JSONArray();
    private boolean bindingConditions,conditionsInFlight,conditionsNeedRecalc,keyboardVisible;
    private long conditionsRevision;
    private LocalWeather localWeather;
    private Button localWeatherButton;
    private boolean weatherPermissionPending,weatherAfterPermission,weatherPermissionManual;
    private String weatherError;
    private final Runnable weatherAuto=this::maybeAutofillWeather;
    private JSONObject settings() throws Exception {
        JSONObject state=new JSONObject(preferences.getString("settings","{}"));
        state.put("easy_hr",preferences.getInt("easy_hr",134));
        state.put("interval_mode","session");
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
    private void initializeTargetSettings(){
        try{
            JSONObject state=new JSONObject(preferences.getString("settings","{}"));
            JSONObject defaults=new JSONObject()
                .put("target_prediction_adjust_elevation",true).put("target_prediction_adjust_temperature",true)
                .put("target_prediction_mode",state.optString("prediction_mode","observed"))
                .put("target_trial_adjust_elevation",state.optBoolean("adjust_elevation",false))
                .put("target_trial_adjust_temperature",state.optBoolean("adjust_temperature",false));
            boolean changed=false;java.util.Iterator<String> keys=defaults.keys();
            while(keys.hasNext()){String key=keys.next();if(!state.has(key)){state.put(key,defaults.get(key));changed=true;}}
            if(!state.has("target_gain_per_mile")){
                state.put("target_gain_per_mile","0").put("target_loss_per_mile","0");changed=true;
                double gain=state.optDouble("target_gain",0),loss=state.optDouble("target_loss",0);
                if(gain!=0||loss!=0)state.put("target_legacy_elevation",String.format(Locale.getDefault(),"Previous totals: +%.0f / −%.0f ft. Enter per-mile rates or choose a route.",gain,loss));
            }
            if(!state.has("target_easy_minutes")){state.put("target_easy_minutes",45).put("target_easy_long_minutes",80);changed=true;}
            if(state.has("target_route_id")&&state.optInt("target_route_engine")!=2){state.put("target_route_engine",2);state.remove("target_route_reference");state.remove("target_interval_rates");changed=true;}
            if(changed)preferences.edit().putString("settings",state.toString()).apply();
        }catch(Exception error){android.util.Log.w("RunDashboard","Could not initialize target basis settings");}
    }
    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);setIntent(intent);
        pendingSample=intent.getData();handleSampleRequest();
    }

    @Override public void onCreate(Bundle state) {
        preferences=getSharedPreferences("training",0);
        palette=MaterialUi.palette(this);ink=palette.ink;muted=palette.muted;
        setTheme(getResources().getIdentifier(palette.dark?"Theme.RunDashboard.Dark":"Theme.RunDashboard.Light","style",getPackageName()));
        super.onCreate(state);
        if(state!=null){restoreScroll=true;screen=state.getInt("screen",TARGETS);profileOpen=screen==PROFILE;runFilter=state.getString("run_filter","all");query=state.getString("query","");int[] positions=state.getIntArray("scroll_positions");if(positions!=null)System.arraycopy(positions,0,scrollPositions,0,Math.min(positions.length,SCREEN_COUNT));}
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_SECURE,WindowManager.LayoutParams.FLAG_SECURE);
        getWindow().setStatusBarColor(palette.surface);
        getWindow().setNavigationBarColor(palette.container);
        getWindow().getDecorView().setSystemUiVisibility(palette.dark?0:View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        store=new SessionStore(getApplicationContext());
        preferences=getSharedPreferences("training",0);
        localWeather=new LocalWeather(getApplicationContext());
        initializeTargetSettings();
        if(!preferences.getBoolean("ux_defaults_v1",false)){
            android.content.SharedPreferences.Editor defaults=preferences.edit().putBoolean("ux_defaults_v1",true);
            if(preferences.getInt("days",0)==0)defaults.putInt("days",90);
            defaults.apply();
        }
        days=preferences.getInt("days",90);miles=preferences.getBoolean("miles",true);
        pendingSample=getIntent().getData();
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);
        root.setFocusableInTouchMode(true);root.setDescendantFocusability(ViewGroup.FOCUS_BEFORE_DESCENDANTS);
        root.setBackgroundColor(palette.surface);setContentView(root);
        root.setOnApplyWindowInsetsListener((view,insets)-> {
            if(android.os.Build.VERSION.SDK_INT>=30){
                boolean visible=insets.isVisible(android.view.WindowInsets.Type.ime());
                if(keyboardVisible&&!visible)view.post(()->{
                    android.view.WindowInsets current=root.getRootWindowInsets();
                    if(current!=null&&!current.isVisible(android.view.WindowInsets.Type.ime()))finishConditionEditing();
                });
                keyboardVisible=visible;
            }
            view.setPadding(0,insets.getSystemWindowInsetTop(),0,insets.getSystemWindowInsetBottom());
            return insets.consumeSystemWindowInsets();
        });
        LinearLayout header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(dp(20),dp(6),dp(12),dp(6));header.setMinimumHeight(dp(64));
        heading=text("Targets",24,ink,false);header.addView(heading,new LinearLayout.LayoutParams(0,-2,1));
        refreshButton=iconButton(MaterialUi.Icon.SYNC,"Sync training data",this::showSyncSheet);
        header.addView(refreshButton,new LinearLayout.LayoutParams(dp(48),dp(48)));root.addView(header);
        rangeBar=new MaterialUi.ButtonGroup(this,false);rangeBar.setPadding(dp(20),0,dp(20),dp(8));rangeArea=rangeBar;root.addView(rangeBar,new LinearLayout.LayoutParams(-1,-2));
        adjustBar=new LinearLayout(this);adjustBar.setVisibility(View.GONE);
        scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setClipToPadding(false);
        content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(20),dp(8),dp(20),dp(24));scroll.addView(content);
        pullRefresh=new PullRefreshLayout(this,scroll,this::loadRuns);
        root.addView(pullRefresh,new LinearLayout.LayoutParams(-1,0,1));
        statusBar=section();statusBar.setBackgroundColor(palette.high);statusBar.setPadding(dp(16),dp(8),dp(16),dp(8));
        LinearLayout status=section();
        message=text("Starting…",12,muted,false);message.setMaxLines(2);message.setEllipsize(TextUtils.TruncateAt.END);
        message.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        status.addView(message,new LinearLayout.LayoutParams(-1,-2));
        MaterialUi.ButtonGroup syncActions=new MaterialUi.ButtonGroup(this,false);status.addView(syncActions,new LinearLayout.LayoutParams(-1,-2));
        pauseButton=actionButton("Pause",false,()->{});pauseButton.setOnClickListener(v->SyncService.pause(this));
        syncActions.addView(pauseButton);pauseButton.setVisibility(View.GONE);
        logButton=actionButton("Details",false,()->{});logButton.setOnClickListener(v->showSyncSheet());
        syncActions.addView(logButton);logButton.setVisibility(View.GONE);statusBar.addView(status);
        downloadProgress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);
        downloadProgress.setIndeterminateTintList(ColorStateList.valueOf(palette.primary));
        downloadProgress.setProgressTintList(ColorStateList.valueOf(palette.primary));
        LinearLayout.LayoutParams progressLp=new LinearLayout.LayoutParams(-1,dp(4));progressLp.topMargin=dp(4);statusBar.addView(downloadProgress,progressLp);
        root.addView(statusBar);statusBar.setVisibility(View.GONE);
        message.addTextChangedListener(new TextWatcher(){
            public void beforeTextChanged(CharSequence value,int start,int count,int after){}
            public void onTextChanged(CharSequence value,int start,int before,int count){
                statusBar.setVisibility(value.length()>0?View.VISIBLE:View.GONE);
                String current=value.toString();message.postDelayed(()->{if(!busy&&!syncRunning&&message.getCurrentTextColor()!=palette.error&&message.getText().toString().equals(current))statusBar.setVisibility(View.GONE);},5000);
            }
            public void afterTextChanged(Editable value){}
        });
        navigation=new LinearLayout(this);navigation.setPadding(dp(4),0,dp(4),0);navigation.setBackgroundColor(palette.container);
        String[] names={"Trends","Sessions","Targets","Profile"};
        for(int destination:new int[]{TARGETS,TRENDS,SESSIONS,PROFILE}){
            final int tab=destination;tabs[tab]=new MaterialUi.NavigationItem(this,names[tab],tab,palette);
            tabs[tab].setOnClickListener(v->selectScreen(tab));navigation.addView(tabs[tab],new LinearLayout.LayoutParams(0,-2,1));
        }
        root.addView(navigation);updateChrome();
        seenSyncCompletion=SyncService.completedId();
        if(SyncService.isRunning()){
            authenticated=true;backendReady=true;renderRuns(null);
        }else execute("Starting the app…",()->BackendRuntime.initialize(getApplicationContext()),result->{
            backendReady=true;render(result);
            if(authenticated)loadDashboard(false);
        });
    }
    @Override protected void onSaveInstanceState(Bundle state){
        scrollPositions[screen]=scroll.getScrollY();state.putInt("screen",screen);state.putString("run_filter",runFilter);state.putString("query",query);state.putIntArray("scroll_positions",scrollPositions);super.onSaveInstanceState(state);
    }
    @Override protected void onStart(){super.onStart();SyncService.listen(syncListener);}
    @Override protected void onResume(){
        super.onResume();foreground=true;resumeSyncIfNeeded();
        if(screen==TARGETS&&profileDirty&&backendReady&&!busy)loadDashboard(false);
        if(weatherAfterPermission){weatherAfterPermission=false;requestLocalWeather(weatherPermissionManual);}
        conditionsHandler.post(weatherAuto);updateWeatherControls();
    }
    @Override protected void onPause(){foreground=false;super.onPause();}
    @Override protected void onStop(){
        conditionsRevision++;if(conditionsRefresh!=null)conditionsHandler.removeCallbacks(conditionsRefresh);
        conditionsHandler.removeCallbacks(weatherAuto);if(localWeather!=null)localWeather.cancel();
        SyncService.unlisten(syncListener);super.onStop();
    }
    @Override protected void onDestroy(){if(localWeather!=null)localWeather.close();conditionsHandler.removeCallbacksAndMessages(null);SyncService.unlisten(syncListener);super.onDestroy();}
    private void restoreSavedScroll(){if(restoreScroll){restoreScroll=false;scroll.post(()->scroll.scrollTo(0,scrollPositions[screen]));}}
    private void resumeSyncIfNeeded(){
        if(foreground&&backendReady&&authenticated&&!busy&&SyncService.canResume(this)){
            try{requestSyncNotifications();SyncService.resume(this,days,settings().toString());}
            catch(Exception error){message.setText("Couldn't resume sync. Tap Refresh to try again.");}
        }
    }
    private void onSyncChanged(SyncService.Snapshot state){
        if(isDestroyed())return;
        if(state.running){
            boolean starting=!syncRunning;
            authenticated=true;syncRunning=true;busy=true;
            if(starting){enable(content,false);updateChrome();}
            downloadProgress.setVisibility(View.VISIBLE);
            downloadProgress.setIndeterminate(state.total<=0);
            if(state.total>0){downloadProgress.setMax(state.total);downloadProgress.setProgress(state.completed);}
            message.setTextColor(muted);message.setText(state.label);recordProgress(state.label);
        }else if(state.id!=seenSyncCompletion){
            seenSyncCompletion=state.id;syncRunning=false;busy=false;enable(content,true);
            downloadProgress.setVisibility(View.GONE);refreshButton.setContentDescription("Sync training data");
            if(state.result!=null&&state.result.optBoolean("ok")){profileDirty=false;renderRuns(state.result);restoreSavedScroll();}
            else updateChrome();
            String status=state.error==null?state.label:state.error;
            JSONArray warnings=state.result==null?null:state.result.optJSONArray("warnings");
            if(state.error==null&&warnings!=null&&warnings.length()>0)status+=" · "+warnings.optString(0);
            message.setTextColor(state.error==null?muted:palette.error);message.setText(status);recordProgress(status);
            handleSampleRequest();
            conditionsHandler.post(weatherAuto);
        }
    }
    private int dp(int value) {return (int)(value*getResources().getDisplayMetrics().density+.5f);}
    private GradientDrawable shape(int color,int radius) {GradientDrawable d=new GradientDrawable(); d.setColor(color); d.setCornerRadius(dp(radius)); return d;}
    private TextView text(String value,int size,int color,boolean bold) {
        TextView v=new TextView(this); v.setText(value); v.setTextSize(size); v.setTextColor(color);
        v.setTypeface(Typeface.create(bold?"sans-serif-medium":"sans-serif",Typeface.NORMAL));v.setLineSpacing(dp(2),1); return v;
    }
    private TextView addText(LinearLayout parent,String value,int size,int color,boolean bold,int top) {
        TextView v=text(value,size,color,bold); LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2); lp.topMargin=dp(top); parent.addView(v,lp); return v;
    }
    private EditText input(String label,int type) {return input(content,label,type);}
    private EditText input(LinearLayout parent,String label,int type) {
        TextView caption=addText(parent,label,13,ink,true,18);
        EditText field=new EditText(this);field.setId(View.generateViewId());caption.setLabelFor(field.getId()); field.setSingleLine(true); field.setInputType(type); field.setTextColor(ink);
        field.setSaveEnabled(false); field.setTextSize(16);field.setMinimumHeight(dp(56));field.setHintTextColor(muted); field.setPadding(dp(12),dp(12),dp(12),dp(12)); field.setBackground(inputBackground());
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2); lp.topMargin=dp(8); parent.addView(field,lp); return field;
    }
    private GradientDrawable outlined(int color,int radius){GradientDrawable d=shape(color,radius);d.setStroke(dp(1),palette.outline);return d;}
    private Drawable inputBackground(){
        android.graphics.drawable.StateListDrawable states=new android.graphics.drawable.StateListDrawable();
        GradientDrawable focused=shape(palette.high,12);focused.setStroke(dp(2),palette.primary);
        states.addState(new int[]{android.R.attr.state_focused},focused);states.addState(new int[]{},outlined(palette.high,12));return states;
    }
    private Button actionButton(String title,boolean primary,Runnable action){
        Button b=new Button(this);b.setText(title);b.setAllCaps(false);b.setTextSize(14);b.setMinHeight(dp(48));b.setMinimumHeight(dp(48));b.setMinWidth(0);b.setMinimumWidth(0);b.setPadding(dp(16),dp(8),dp(16),dp(8));
        b.setSingleLine(false);b.setMaxLines(Integer.MAX_VALUE);b.setHorizontallyScrolling(false);b.setEllipsize(null);b.setIncludeFontPadding(true);b.setGravity(Gravity.CENTER);
        b.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));
        int foreground=primary?palette.onPrimary:palette.primary;
        b.setTextColor(new ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled},new int[]{}},new int[]{(ink&0xffffff)|0x61000000,foreground}));
        b.setBackground(MaterialUi.ripple(this,primary?palette.primary:palette.high,24,foreground));
        b.setOnClickListener(v->{if(!busy)action.run();});return b;
    }
    private Button iconButton(int icon,String description,Runnable action){
        Button b=actionButton("",false,action);b.setTextSize(0);b.setPadding(dp(12),dp(12),dp(12),dp(12));
        MaterialUi.Icon drawable=new MaterialUi.Icon(icon,palette.primary);drawable.setBounds(0,0,dp(24),dp(24));
        b.setCompoundDrawables(drawable,null,null,null);b.setContentDescription(description);b.setBackground(MaterialUi.ripple(this,palette.surface,24,palette.primary));
        b.setOnClickListener(v->action.run());return b;
    }
    private Button chipButton(String label,boolean selected,Runnable action){
        Button b=actionButton(label,false,action);b.setTextColor(selected?palette.onPrimaryContainer:muted);
        Drawable background=selected?shape(palette.primaryContainer,16):outlined(palette.surface,16);
        b.setBackground(new android.graphics.drawable.RippleDrawable(ColorStateList.valueOf((palette.primary&0xffffff)|0x24000000),background,shape(Color.WHITE,16)));
        b.setSelected(selected);b.setTextSize(13);return b;
    }
    private Button button(String title,boolean primary,Runnable action) {return button(content,title,primary,action);}
    private Button button(LinearLayout parent,String title,boolean primary,Runnable action) {
        Button b=actionButton(title,primary,action);
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(12);parent.addView(b,lp);return b;
    }
    private LinearLayout card() {
        return card(content);
    }
    private LinearLayout card(LinearLayout parent) {
        LinearLayout panel=new LinearLayout(this);panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(20),dp(20),dp(20),dp(20));panel.setBackground(panelShape());
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.bottomMargin=dp(16);parent.addView(panel,lp);return panel;
    }
    private GradientDrawable panelShape(){return shape(palette.container,24);}
    private static final class SheetScroll extends ScrollView {
        SheetScroll(android.content.Context context){super(context);setFillViewport(false);}
        @Override protected void onMeasure(int width,int height){
            int limit=(int)(getResources().getDisplayMetrics().heightPixels*.65f);
            if(MeasureSpec.getMode(height)!=MeasureSpec.UNSPECIFIED)limit=Math.min(limit,MeasureSpec.getSize(height));
            super.onMeasure(width,MeasureSpec.makeMeasureSpec(limit,MeasureSpec.AT_MOST));
        }
    }
    private Dialog bottomSheet(String title,View body,String saveLabel,Consumer<Dialog> onSave){
        Dialog dialog=new Dialog(this);dialog.requestWindowFeature(android.view.Window.FEATURE_NO_TITLE);
        LinearLayout sheet=section();sheet.setPadding(dp(20),dp(8),dp(20),dp(20));sheet.setBackground(shape(palette.container,28));
        View handle=new View(this);handle.setBackground(shape(palette.outline,2));LinearLayout.LayoutParams handleLp=new LinearLayout.LayoutParams(dp(32),dp(4));handleLp.gravity=Gravity.CENTER_HORIZONTAL;handleLp.bottomMargin=dp(8);sheet.addView(handle,handleLp);
        LinearLayout bar=new LinearLayout(this);bar.setGravity(Gravity.CENTER_VERTICAL);
        TextView label=text(title,22,ink,false);bar.addView(label,new LinearLayout.LayoutParams(0,-2,1));
        Button close=iconButton(MaterialUi.Icon.CLOSE,"Close "+title,dialog::dismiss);bar.addView(close,new LinearLayout.LayoutParams(dp(48),dp(48)));sheet.addView(bar);
        SheetScroll wrapper=new SheetScroll(this);wrapper.addView(body);sheet.addView(wrapper,new LinearLayout.LayoutParams(-1,-2));
        if(saveLabel!=null){Button save=button(sheet,saveLabel,true,()->{});save.setOnClickListener(v->{if(!busy&&onSave!=null)onSave.accept(dialog);});}
        dialog.setContentView(sheet);dialog.getWindow().setBackgroundDrawableResource(android.R.color.transparent);
        dialog.getWindow().setFlags(WindowManager.LayoutParams.FLAG_SECURE,WindowManager.LayoutParams.FLAG_SECURE);
        dialog.getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        dialog.getWindow().setNavigationBarColor(palette.container);dialog.show();
        dialog.getWindow().setGravity(Gravity.BOTTOM);dialog.getWindow().setLayout(-1,-2);return dialog;
    }
    private Dialog fullScreen(String title,View body,Consumer<PopupMenu> menu){
        Dialog dialog=new Dialog(this);dialog.requestWindowFeature(android.view.Window.FEATURE_NO_TITLE);
        LinearLayout page=section();page.setBackgroundColor(palette.surface);
        page.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(0,insets.getSystemWindowInsetTop(),0,insets.getSystemWindowInsetBottom());return insets.consumeSystemWindowInsets();});
        LinearLayout toolbar=new LinearLayout(this);toolbar.setGravity(Gravity.CENTER_VERTICAL);toolbar.setPadding(dp(4),dp(4),dp(8),dp(4));
        Button close=iconButton(MaterialUi.Icon.BACK,"Back",dialog::dismiss);toolbar.addView(close,new LinearLayout.LayoutParams(dp(48),dp(48)));
        TextView name=text(title,22,ink,false);name.setMaxLines(1);name.setEllipsize(TextUtils.TruncateAt.END);toolbar.addView(name,new LinearLayout.LayoutParams(0,-2,1));
        if(menu!=null){Button more=iconButton(MaterialUi.Icon.MORE,"Session actions",()->{});more.setOnClickListener(v->{PopupMenu popup=new PopupMenu(this,more);menu.accept(popup);popup.show();});toolbar.addView(more,new LinearLayout.LayoutParams(dp(48),dp(48)));}
        page.addView(toolbar);ScrollView wrapper=new ScrollView(this);wrapper.setFillViewport(true);wrapper.addView(body);page.addView(wrapper,new LinearLayout.LayoutParams(-1,0,1));
        dialog.setContentView(page);dialog.getWindow().setBackgroundDrawableResource(android.R.color.transparent);
        dialog.getWindow().setFlags(WindowManager.LayoutParams.FLAG_SECURE,WindowManager.LayoutParams.FLAG_SECURE);
        dialog.getWindow().setStatusBarColor(palette.surface);dialog.getWindow().setNavigationBarColor(palette.surface);
        dialog.getWindow().getDecorView().setSystemUiVisibility(palette.dark?0:View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        dialog.show();dialog.getWindow().setLayout(-1,-1);return dialog;
    }
    private MaterialUi.ButtonGroup segmented(LinearLayout parent,String[] labels,int selected,java.util.function.IntConsumer choose){
        MaterialUi.ButtonGroup group=new MaterialUi.ButtonGroup(this,true);
        for(int i=0;i<labels.length;i++){
            final int option=i;Button control=chipButton(labels[i],selected==i,()->choose.accept(option));control.setTextSize(13);control.setPadding(dp(8),dp(8),dp(8),dp(8));
            control.setAccessibilityDelegate(new View.AccessibilityDelegate(){@Override public void onInitializeAccessibilityNodeInfo(View host,android.view.accessibility.AccessibilityNodeInfo info){super.onInitializeAccessibilityNodeInfo(host,info);info.setClassName("android.widget.RadioButton");info.setCheckable(true);info.setChecked(option==selected);}});
            group.addView(control);
        }
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(12);parent.addView(group,lp);return group;
    }
    private void showSyncSheet(){
        LinearLayout body=section();syncSheetStatus=addText(body,syncRunning?message.getText().toString():"Your saved training data stays available during sync.",15,ink,false,8);
        String stamp=preferences.getString("last_sync","");addText(body,stamp.isEmpty()?"No completed sync yet":"Last checked · "+stamp,13,muted,false,8);
        final Dialog[] sheet={null};
        if(syncRunning){Button pause=button(body,"Pause sync",true,()->{});pause.setOnClickListener(v->{SyncService.pause(this);sheet[0].dismiss();});}
        else{Button sync=button(body,"Sync now",true,()->{sheet[0].dismiss();loadRuns();});sync.setEnabled(authenticated&&!busy);}
        if(dashboardData!=null){JSONObject coverage=dashboardData.optJSONObject("sync");
            String[] keys={"recovery","hr_recordings","interval_recordings","trial_recordings","weather","terrain"};String[] names={"Recovery","Easy recordings","Interval recordings","5K recordings","Weather","Terrain"};
            for(int i=0;coverage!=null&&i<keys.length;i++){JSONObject count=coverage.optJSONObject(keys[i]);if(count!=null)addText(body,names[i]+" · "+count.optInt("done")+" saved · "+count.optInt("pending")+" pending",14,muted,false,12);}
        }
        Button logs=button(body,"View sync log",false,()->{});logs.setEnabled(syncLog.length()>0);logs.setOnClickListener(v->{sheet[0].dismiss();showSyncLog();});
        sheet[0]=bottomSheet("Training data",body,null,null);sheet[0].setOnDismissListener(d->syncSheetStatus=null);
    }
    private void showSyncLog(){
        logView=text(syncLog.toString(),14,ink,false);logView.setPadding(dp(16),dp(12),dp(16),dp(12));logView.setTextIsSelectable(true);
        ScrollView logs=new ScrollView(this);logs.addView(logView);
        new AlertDialog.Builder(this).setTitle(busy?"Updating dashboard…":"Update log").setView(logs).setPositiveButton("Close",(d,w)->logView=null).setOnDismissListener(d->logView=null).show();
    }
    private void recordProgress(String label){
        syncLog.append(label).append('\n');if(syncLog.length()>20000)syncLog.delete(0,syncLog.length()-16000);
        if(logView!=null)logView.setText(syncLog.toString());if(syncSheetStatus!=null)syncSheetStatus.setText(label);if(logButton!=null)logButton.setVisibility(syncRunning?View.VISIBLE:View.GONE);
    }
    private void updateChrome(){
        pullRefresh.setRefreshEnabled(authenticated&&!busy&&screen!=PROFILE);
        pullRefresh.setRefreshing(syncRunning);
        heading.setText(new String[]{"Trends","Sessions","Targets","Profile"}[screen]);
        refreshButton.setVisibility(authenticated?View.VISIBLE:View.GONE);refreshButton.setEnabled(true);
        refreshButton.setContentDescription(syncRunning?"Sync in progress. Open controls":"Sync training data");
        rangeArea.setVisibility(authenticated&&(screen==TRENDS||screen==SESSIONS)?View.VISIBLE:View.GONE);
        pauseButton.setVisibility(syncRunning?View.VISIBLE:View.GONE);logButton.setVisibility(syncRunning?View.VISIBLE:View.GONE);
        adjustBar.setVisibility(View.GONE);rangeBar.removeAllViews();
        int[] windows={0,7,30,45,90,180,365,548,730,-1};
        String[] labels={"All history","7 days","30 days","45 days","90 days","180 days","1 year","18 months","24 months","Custom dates"};
        String[] choices={"All (since June 2025)","Last 7 days","Last 30 days","Last 45 days","Last 90 days","Last 180 days","Last year","Last 18 months","Last 24 months","Custom dates…"};
        int selected=4;for(int i=0;i<windows.length;i++)if(days==windows[i])selected=i;final int chosen=selected;
        Button range=chipButton(labels[selected]+" ▾",false,()->new AlertDialog.Builder(this).setTitle("Date range")
            .setSingleChoiceItems(choices,chosen,(dialog,which)->{dialog.dismiss();if(windows[which]==-1)chooseDates();else changeRange(windows[which]);}).setNegativeButton("Cancel",null).show());
        range.setEnabled(!busy);rangeBar.addView(range,new LinearLayout.LayoutParams(-2,-2));
        if(screen==TRENDS||screen==SESSIONS){
            boolean elevation=adjusted("adjust_elevation"),weather=adjusted("adjust_temperature"),both=elevation&&weather;
            rangeBar.addView(adjustmentControl(elevation,weather,()->applyAdjustments(!both,!both),this::editAdjustments));
        }
        for(int i=0;i<tabs.length;i++)tabs[i].setActive(screen==i);
    }
    private void changeRange(int range) {
        if(days==range)return;days=range;preferences.edit().putInt("days",days).apply();updateChrome();loadDashboard(false);
    }
    private void selectScreen(int target) {
        if(target==screen)return;
        scrollPositions[screen]=scroll.getScrollY();screen=target;profileOpen=screen==PROFILE;
        android.view.inputmethod.InputMethodManager keyboard=(android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE);
        keyboard.hideSoftInputFromWindow(content.getWindowToken(),0);
        if(profileOpen)renderProfile();else if(authenticated)renderRuns(null);else renderWelcome();
        if(busy)enable(content,false);
        scroll.post(()->scroll.scrollTo(0,scrollPositions[screen]));
        if(!busy&&authenticated&&screen!=PROFILE&&profileDirty)loadDashboard(false);
    }
    private void render(JSONObject state) {
        authenticated=state.optBoolean("authenticated");needsMfa=state.optBoolean("needs_mfa");
        if(needsMfa){screen=PROFILE;profileOpen=true;}
        if(profileOpen)renderProfile();else if(authenticated)renderRuns(null);else renderWelcome();
    }
    private void renderWelcome() {
        content.removeAllViews();updateChrome();LinearLayout panel=card();
        addText(panel,"Your training, over time",26,ink,true,0);
        addText(panel,"Track easy-run pace, compare your intervals, and follow your 5K times.",16,muted,false,12);
        Button connect=actionButton("Connect Garmin",true,()->selectScreen(PROFILE));
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(24);panel.addView(connect,lp);
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
                execute("Verifying your code…",()->invoke("verify",value),result->{code.setText("");render(result);if(authenticated){profileOpen=false;screen=TARGETS;renderRuns(null);loadRuns();}});
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
                execute("Signing in to Garmin. This may take a minute…",()->{store.clear();SyncService.clear(this);return invoke("login",user,pass);},result->{render(result);if(authenticated){profileOpen=false;screen=TARGETS;renderRuns(null);loadRuns();}});
            });
            addText(parent,"Your password goes to Garmin over HTTPS and isn't saved. Your session is encrypted on this phone. Personal prototype using an unofficial Garmin connection.",12,muted,false,20);
        }
    }
    @Override public void onBackPressed(){
        if(isConditionField(getCurrentFocus())){finishConditionEditing();return;}
        if(screen!=TARGETS){selectScreen(TARGETS);return;}
        super.onBackPressed();
    }
    private boolean isConditionField(View view){
        if(screen!=TARGETS||conditionsFields==null||view==null)return false;
        if(view==raceDistanceField)return true;
        for(EditText field:conditionsFields)if(field==view)return true;return false;
    }
    private boolean touches(View view,android.view.MotionEvent event){
        android.graphics.Rect bounds=new android.graphics.Rect();
        return view!=null&&view.isShown()&&view.getGlobalVisibleRect(bounds)&&bounds.contains((int)event.getRawX(),(int)event.getRawY());
    }
    private void finishConditionEditing(){
        View focused=getCurrentFocus();if(!isConditionField(focused))return;
        if(focused==raceDistanceField)saveInlineRaceDistance();else saveInlineConditions();root.requestFocus();
        ((android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(focused.getWindowToken(),0);
    }
    @Override public boolean dispatchTouchEvent(android.view.MotionEvent event){
        if(event.getActionMasked()==android.view.MotionEvent.ACTION_DOWN&&isConditionField(getCurrentFocus())){
            boolean anotherField=touches(raceDistanceField,event);for(EditText field:conditionsFields)if(touches(field,event)){anotherField=true;break;}
            if(!anotherField)finishConditionEditing();
        }
        return super.dispatchTouchEvent(event);
    }
    private void renderProfile() {
        profileOpen=true;screen=PROFILE;content.removeAllViews();updateChrome();
        LinearLayout account=card();
        if(authenticated){
            addText(account,"Garmin Connect",22,ink,false,0);
            addText(account,"● Connected",14,palette.primary,true,8);
            button(account,"Sign out",false,()->new AlertDialog.Builder(this).setTitle("Sign out of Garmin?")
                .setMessage("This removes your saved Garmin session, downloaded runs and run corrections from this phone. Your display settings are kept.")
                .setNegativeButton("Cancel",null).setPositiveButton("Sign out",(d,w)->logout()).show());
        }else renderAuthentication(account);
        if(authenticated)renderSyncCard();
        LinearLayout display=card();addText(display,"Display",22,ink,false,0);
        addText(display,"Appearance",14,muted,true,16);
        String appearance=preferences.getString("appearance","system");String[] appearances={"system","light","dark"};int appearanceIndex=appearance.equals("dark")?2:appearance.equals("light")?1:0;
        segmented(display,new String[]{"System","Light","Dark"},appearanceIndex,choice->{if(!appearances[choice].equals(appearance)){preferences.edit().putString("appearance",appearances[choice]).apply();recreate();}});
        addText(display,"Pace & distance",14,muted,true,20);
        segmented(display,new String[]{"Miles","Kilometres"},miles?0:1,choice->{boolean useMiles=choice==0;if(miles!=useMiles){miles=useMiles;preferences.edit().putBoolean("miles",miles).apply();renderProfile();}});
        addText(display,"5K times always use minutes:seconds.",12,muted,false,16);
        renderRouteProfile();
        LinearLayout sync=card();addText(sync,"Data sources",22,ink,false,0);
        String[] syncKeys={"full_history","include_recovery","include_weather","include_station_weather","include_recordings","include_terrain"};String[] syncLabels={"Use full history for predictions and targets","Download sleep, resting HR & HRV","Download Garmin activity weather","Prefer nearby KPVU / KSLC station weather","Read original FIT interval and HR metrics","Terrain elevation: send sampled routes to OpenTopoData"};
        for(int i=0;i<syncKeys.length;i++){
            final String key=syncKeys[i];Switch choice=new Switch(this);choice.setText(syncLabels[i]);choice.setTextSize(14);choice.setTextColor(ink);choice.setPadding(0,dp(12),0,dp(12));choice.setSwitchPadding(dp(12));choice.setMinHeight(dp(64));choice.setChecked(preferences.getBoolean(key,!key.equals("include_terrain")));sync.addView(choice,new LinearLayout.LayoutParams(-1,-2));
            choice.setOnCheckedChangeListener((v,checked)->{preferences.edit().putBoolean(key,checked).apply();profileDirty=true;});
        }
        addText(sync,"Recovery downloads use date-range summaries. Later syncs reuse saved history. Sign-out clears saved health and activity data.",12,muted,false,10);
        button(sync,"Classification: "+setting("classification_mode","web")+" ▾",false,()->chooseMode("Automatic categories","classification_mode",new String[]{"Web rules (including injury / rebuild dates)","Original Android title / HR suggestions"},new String[]{"web","native"}));
        LinearLayout heart=card();addText(heart,"Easy-run heart rate",22,ink,false,0);
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
        EditText maximum=input(heart,"Maximum heart rate (intensity normalization)",InputType.TYPE_CLASS_NUMBER);maximum.setText(Integer.toString(preferences.getInt("max_hr",191)));
        button(heart,"Save maximum HR",false,()->{try{int hr=Integer.parseInt(maximum.getText().toString());if(hr<80||hr>240)throw new NumberFormatException();preferences.edit().putInt("max_hr",hr).apply();profileDirty=true;message.setText("Maximum HR saved.");}catch(NumberFormatException e){maximum.setError("Use 80–240 bpm");}});
        addText(heart,"A low average can include higher peaks. Interval and trial titles take priority. You can correct any category in Sessions.",12,muted,false,12);
    }
    private void renderRuns(JSONObject data) {
        if(data!=null)dashboardData=data;
        if(screen==PROFILE){renderProfile();return;}
        profileOpen=false;content.removeAllViews();updateChrome();
        if(dashboardData==null){addText(content,SyncService.isRunning()?"Syncing your training data. You can leave the app while it downloads.":"Your charts will appear after the first download.",16,muted,false,20);return;}
        if(screen==SESSIONS)renderSessions();else if(screen==TARGETS)renderTargets();else renderTrends();
    }
    private void renderSyncCard(){
        LinearLayout panel=card();addText(panel,"Sync",22,ink,false,0);
        JSONObject state=dashboardData==null?null:dashboardData.optJSONObject("sync");
        int pending=0;
        if(state!=null){
            String[] enabled={"include_terrain","include_recovery","include_recordings","include_recordings","include_recordings","include_weather"};
            String[] keys={"terrain","recovery","hr_recordings","interval_recordings","trial_recordings","weather"};
            for(int i=0;i<keys.length;i++)if(preferences.getBoolean(enabled[i],!enabled[i].equals("include_terrain"))){JSONObject count=state.optJSONObject(keys[i]);if(count!=null)pending+=count.optInt("pending");}
        }
        boolean complete=state!=null&&state.optBoolean("summaries_complete")&&pending==0;
        addText(panel,complete?"Saved downloads complete":pending>0?pending+" downloads pending":"Refresh to check for new activities",16,ink,true,10);
        String stamp=preferences.getString("last_sync","");
        addText(panel,stamp.isEmpty()?"Sync now to record the latest check":"Last sync check · "+stamp,13,muted,false,6);
        button(panel,"Sync now",true,this::loadRuns);
        button(panel,"Sync controls & progress",false,this::showSyncSheet);
        if(syncLog.length()>0)button(panel,"View sync log",false,this::showSyncLog);
        button(panel,syncDetailsOpen?"Hide details ▴":"Details ▾",false,()->{syncDetailsOpen=!syncDetailsOpen;renderProfile();});
        if(syncDetailsOpen){
            if(state!=null){
                String[] keys={"terrain","recovery","hr_recordings","interval_recordings","trial_recordings","weather"};
                String[] names={"Terrain routes","Recovery downloads","Easy HR recordings","Interval recordings","5K recordings","Garmin weather"};
                for(int i=0;i<keys.length;i++){
                    JSONObject count=state.optJSONObject(keys[i]);if(count==null)continue;int skipped=count.optInt("skipped");
                    addText(panel,names[i]+": "+count.optInt("done")+" / "+count.optInt("total")+(skipped>0?" · "+skipped+" unavailable":"")+" · "+count.optInt("pending")+" pending",14,muted,false,8);
                }
            }
            addText(panel,"Terrain lookups send sampled route coordinates to OpenTopoData; only elevation totals are saved. Completed routes are reused. Downloads continue in the background; Pause stops after the current request.",13,muted,false,12);
            button(panel,"Download / resume terrain",false,this::loadTerrain);
        }
        if(dashboardData!=null){JSONArray warnings=dashboardData.optJSONArray("warnings");if(warnings!=null)for(int i=0;i<warnings.length();i++)addText(panel,warnings.optString(i),13,muted,false,8);}
    }

    private boolean adjusted(String key){return "true".equals(setting(key,"false"));}
    private LinearLayout adjustmentControl(boolean elevation,boolean weather,Runnable toggleBoth,Runnable edit){
        boolean both=elevation&&weather,any=elevation||weather;int foreground=any?palette.onPrimaryContainer:muted;
        LinearLayout control=new LinearLayout(this);control.setGravity(Gravity.CENTER_VERTICAL);control.setBaselineAligned(false);
        control.setBackground(any?shape(palette.primaryContainer,16):outlined(palette.surface,16));
        Button toggle=chipButton("Adjustments · "+(both?"On":any?"1":"Off"),any,toggleBoth);
        toggle.setPadding(dp(12),dp(8),dp(12),dp(8));toggle.setBackground(MaterialUi.ripple(this,Color.TRANSPARENT,16,foreground));toggle.setEnabled(!busy);
        String state=both?"Both on":elevation?"Elevation only":weather?"Weather only":"Both off";
        toggle.setContentDescription("Pace adjustments. "+state+". Turn both "+(both?"off":"on")+".");
        control.addView(toggle,new LinearLayout.LayoutParams(0,-2,1));
        View divider=new View(this);divider.setBackgroundColor(palette.outline);control.addView(divider,new LinearLayout.LayoutParams(dp(1),dp(24)));
        Button more=iconButton(MaterialUi.Icon.MORE,"Choose elevation and weather adjustments separately",()->{if(!busy)edit.run();});
        more.setTooltipText("Choose individual adjustments");more.setEnabled(!busy);more.setBackground(MaterialUi.ripple(this,Color.TRANSPARENT,16,foreground));
        control.addView(more,new LinearLayout.LayoutParams(dp(48),dp(48)));return control;
    }
    private String adjustmentLabel(){
        return adjusted("adjust_elevation")?(adjusted("adjust_temperature")?"Elevation + weather":"Elevation"):(adjusted("adjust_temperature")?"Weather":"No condition adjustments");
    }
    private void applyAdjustments(boolean elevation,boolean weather){
        try{
            JSONObject state=settings();state.put("adjust_elevation",elevation);state.put("adjust_temperature",weather);
            preferences.edit().putString("settings",state.toString()).apply();loadDashboard(false);
        }catch(Exception error){message.setText("Could not save pace adjustments.");}
    }
    private void editAdjustments(){
        LinearLayout form=section();addText(form,"Show equivalent pace for flat or cool conditions where measurements are available. Recorded values remain available in point details.",14,muted,false,8);
        Switch elevation=new Switch(this),weather=new Switch(this);elevation.setText("Elevation");weather.setText("Weather · temperature / dew point");
        elevation.setTextColor(ink);weather.setTextColor(ink);elevation.setMinHeight(dp(64));weather.setMinHeight(dp(64));elevation.setChecked(adjusted("adjust_elevation"));weather.setChecked(adjusted("adjust_temperature"));
        form.addView(elevation,new LinearLayout.LayoutParams(-1,-2));form.addView(weather,new LinearLayout.LayoutParams(-1,-2));
        bottomSheet("Pace adjustments",form,"Apply adjustments",dialog->{dialog.dismiss();applyAdjustments(elevation.isChecked(),weather.isChecked());});
    }
    private void localRender(){int position=scroll.getScrollY();renderRuns(null);scroll.post(()->scroll.scrollTo(0,position));}
    private LinearLayout section(){LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);return box;}
    private void disclosure(LinearLayout parent,String title,View body){
        body.setVisibility(View.GONE);Button toggle=button(parent,title+" ▾",false,()->{});
        toggle.setContentDescription("Show "+title);toggle.setOnClickListener(v->{boolean opening=body.getVisibility()!=View.VISIBLE;body.setVisibility(opening?View.VISIBLE:View.GONE);toggle.setText(title+(opening?" ▴":" ▾"));toggle.setContentDescription((opening?"Hide ":"Show ")+title);});parent.addView(body);
    }
    private void smallButton(ViewGroup parent,String label,Runnable action){
        Button control=chipButton(label,false,action);control.setTextSize(13);LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-2,-2);lp.topMargin=dp(6);lp.rightMargin=dp(6);parent.addView(control,lp);
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
    private void renderTrends(){
        JSONObject data=dashboardData,summary=data.optJSONObject("summary");
        addText(content,"Your training",28,ink,false,0);
        addText(content,dateSpan(data.optString("start"),data.optString("end")),13,muted,false,6);
        if(summary!=null)renderKpis(summary);
        int attention=countAttention();if(attention>0)smallButton(content,attention+" sessions need review →",()->{runFilter="attention";selectScreen(SESSIONS);});
        String selected=preferences.getString("trends_section","5k");
        String[] keys={"5k","pace","load","recovery"},labels={"5K","Pace","Load","Recovery"};
        MaterialUi.ButtonGroup sections=new MaterialUi.ButtonGroup(this,false);sections.setPadding(0,dp(16),0,dp(16));
        for(int i=0;i<keys.length;i++){
            final String key=keys[i];Button chip=chipButton(labels[i],key.equals(selected),()->{
                preferences.edit().putString("trends_section",key).apply();renderRuns(null);
            });chip.setPadding(dp(12),dp(8),dp(12),dp(8));sections.addView(chip);
        }
        content.addView(sections,new LinearLayout.LayoutParams(-1,-2));
        if("pace".equals(selected)){
            chartCard("Interval pace","Session averages",data.optJSONArray("interval_points"),false,new String[]{"short","medium","long"});
            chartCard("Easy pace","Road, treadmill and trail",data.optJSONArray("run_points"),false,new String[]{"easy"});heartCard();
        }else if("load".equals(selected))weeklyCard();
        else if("recovery".equals(selected))recoveryCard();
        else predictionCard();
        JSONArray warnings=data.optJSONArray("warnings");if(warnings!=null)for(int i=0;i<warnings.length();i++)addText(content,warnings.optString(i),14,muted,false,8);
    }
    private void chartHeader(LinearLayout panel,String title,Runnable options){
        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);
        row.addView(text(title,22,ink,false),new LinearLayout.LayoutParams(0,-2,1));
        if(options!=null)row.addView(iconButton(MaterialUi.Icon.MORE,title+" settings",()->{if(!busy)options.run();}),new LinearLayout.LayoutParams(dp(48),dp(48)));
        panel.addView(row,new LinearLayout.LayoutParams(-1,-2));
    }
    private RadioGroup chartChoices(LinearLayout parent,String title,String[] labels,int selected){
        addText(parent,title,14,ink,true,16);RadioGroup group=new RadioGroup(this);
        for(int i=0;i<labels.length;i++){
            RadioButton choice=new RadioButton(this);choice.setId(View.generateViewId());choice.setText(labels[i]);choice.setTextSize(15);choice.setTextColor(ink);
            choice.setMinHeight(dp(48));choice.setPadding(dp(4),dp(8),dp(4),dp(8));choice.setSingleLine(false);group.addView(choice,new RadioGroup.LayoutParams(-1,-2));
            if(i==selected)group.check(choice.getId());
        }
        parent.addView(group,new LinearLayout.LayoutParams(-1,-2));return group;
    }
    private int checkedChoice(RadioGroup group){return group.indexOfChild(group.findViewById(group.getCheckedRadioButtonId()));}
    private void chartLegend(LinearLayout panel,ChartSeries series,Runnable changed){
        if(series.ids.length==0)return;
        MaterialUi.ButtonGroup row=new MaterialUi.ButtonGroup(this,false);row.setPadding(0,dp(8),0,dp(4));
        Button[] items=new Button[series.ids.length];MaterialUi.Marker[] symbols=new MaterialUi.Marker[items.length];
        for(int i=0;i<items.length;i++){
            final int index=i;String id=series.ids[i];
            Button item=actionButton(series.labels[i],false,()->preferences.edit().putBoolean(series.preferenceKey(id),!series.isVisible(id)).apply());
            item.setTextSize(12);item.setPadding(dp(8),dp(8),dp(8),dp(8));item.setBackground(MaterialUi.ripple(this,Color.TRANSPARENT,12,palette.primary));
            MaterialUi.Marker marker=new MaterialUi.Marker(series.markers[i],palette.chart(ScatterPlot.color(series.colors[i])));marker.setBounds(0,0,dp(14),dp(14));
            item.setCompoundDrawables(marker,null,null,null);item.setCompoundDrawablePadding(dp(4));
            item.setAccessibilityDelegate(new View.AccessibilityDelegate(){
                @Override public void onInitializeAccessibilityNodeInfo(View host,android.view.accessibility.AccessibilityNodeInfo info){
                    super.onInitializeAccessibilityNodeInfo(host,info);info.setClassName("android.widget.CheckBox");info.setCheckable(true);info.setChecked(series.isVisible(series.ids[index]));
                }
            });
            items[i]=item;symbols[i]=marker;row.addView(item);
        }
        Runnable refresh=()->{
            for(int i=0;i<items.length;i++){
                String id=series.ids[i];boolean shown=preferences.getBoolean(series.preferenceKey(id),true);series.setVisible(id,shown);
                items[i].setTextColor(shown?ink:muted);symbols[i].setAlpha(shown?255:90);
                int flags=items[i].getPaintFlags();items[i].setPaintFlags(shown?flags&~android.graphics.Paint.STRIKE_THRU_TEXT_FLAG:flags|android.graphics.Paint.STRIKE_THRU_TEXT_FLAG);
                items[i].setContentDescription(series.labels[i]+" series. "+(shown?"Shown. Tap to hide.":"Hidden. Tap to show."));
            }
            if(changed!=null)changed.run();
        };
        android.content.SharedPreferences.OnSharedPreferenceChangeListener listener=(prefs,key)->{
            if(key==null){refresh.run();return;}
            for(String id:series.ids)if(series.preferenceKey(id).equals(key)){refresh.run();return;}
        };
        row.addOnAttachStateChangeListener(new View.OnAttachStateChangeListener(){
            public void onViewAttachedToWindow(View view){preferences.registerOnSharedPreferenceChangeListener(listener);refresh.run();}
            public void onViewDetachedFromWindow(View view){preferences.unregisterOnSharedPreferenceChangeListener(listener);}
        });
        refresh.run();panel.addView(row,new LinearLayout.LayoutParams(-1,-2));
    }
    private void predictionOptions(){
        LinearLayout body=section();RadioGroup mode=chartChoices(body,"Compare pace",new String[]{"Recorded effort","HR-adjusted effort"},"intensity".equals(setting("prediction_mode","observed"))?1:0);
        addText(body,"Visible series",14,ink,true,16);String[] keys={"trial_points","prediction_points","easy_prediction_points"},labels={"Measured 5K","Interval estimate","Easy estimate"};
        CheckBox[] choices=new CheckBox[keys.length];
        for(int i=0;i<keys.length;i++){CheckBox choice=new CheckBox(this);choice.setText(labels[i]);choice.setTextSize(15);choice.setTextColor(ink);choice.setMinHeight(dp(48));choice.setChecked(preferences.getBoolean("show_"+keys[i],true));body.addView(choice,new LinearLayout.LayoutParams(-1,-2));choices[i]=choice;}
        addText(body,"Measured points come from recorded 5K efforts. Dashed lines are calibrated estimates. Easy estimates need at least two nearby trials. Missing condition data stays unadjusted.",14,muted,false,12);
        bottomSheet("5K chart settings",body,"Apply",dialog->{
            for(int i=0;i<keys.length;i++)preferences.edit().putBoolean("show_"+keys[i],choices[i].isChecked()).apply();
            saveSetting("prediction_mode",checkedChoice(mode)==1?"intensity":"observed");dialog.dismiss();loadDashboard(false);
        });
    }
    private void paceOptions(boolean easy){
        LinearLayout body=section();String key=easy?"easy_mode":"interval_pace_mode";
        RadioGroup mode=chartChoices(body,"Compare pace",new String[]{"Recorded effort","HR-adjusted effort"},"intensity".equals(setting(key,"observed"))?1:0);
        RadioGroup scale=easy?chartChoices(body,"Pace scale",new String[]{"Fit to all measurements","Fixed 7:00–10:00 min/mile"},preferences.getBoolean("easy_auto_scale",true)?0:1):null;
        bottomSheet(easy?"Easy pace settings":"Interval pace settings",body,"Apply",dialog->{
            saveSetting(key,checkedChoice(mode)==1?"intensity":"observed");
            if(easy)preferences.edit().putBoolean("easy_auto_scale",checkedChoice(scale)==0).apply();
            dialog.dismiss();loadDashboard(false);
        });
    }
    private String dateSpan(String first,String last){
        try{DateTimeFormatter format=DateTimeFormatter.ofPattern("MMM d, yyyy",Locale.getDefault());return LocalDate.parse(first).format(format)+" – "+LocalDate.parse(last).format(format);}catch(Exception e){return first+" – "+last;}
    }
    private int chartHeight(int base){return dp(Math.round(base*Math.max(1,getResources().getConfiguration().fontScale)));}
    private JSONObject latestPoint(JSONArray points){
        JSONObject latest=null;if(points!=null)for(int i=0;i<points.length();i++){JSONObject point=points.optJSONObject(i);if(point!=null&&(latest==null||point.optString("started",point.optString("date")).compareTo(latest.optString("started",latest.optString("date")))>0))latest=point;}return latest;
    }
    private void predictionCard(){
        LinearLayout panel=card();chartHeader(panel,"5K performance",this::predictionOptions);
        JSONArray estimates=dashboardData.optJSONArray("prediction_points");JSONObject estimate=latestPoint(estimates);
        if(estimate!=null){addText(panel,raceTime(estimate.optDouble("duration")),32,ink,false,8);addText(panel,"Latest interval estimate · "+estimate.optString("date"),13,muted,false,2);}
        JSONArray points=new JSONArray();String[] keys={"trial_points","prediction_points","easy_prediction_points"};
        for(String key:keys){JSONArray source=dashboardData.optJSONArray(key);if(source!=null)for(int j=0;j<source.length();j++)points.put(source.optJSONObject(j));}
        addText(panel,"Dashed lines are estimates · "+adjustmentLabel()+("intensity".equals(setting("prediction_mode","observed"))?" · HR-adjusted effort":""),12,muted,false,4);
        addInteractivePlot(panel,"5K performance",points,null,null,Double.NaN,true,false,ChartSeries.PREDICTION,false);
    }
    private void heartCard(){
        LinearLayout panel=card();boolean average=preferences.getBoolean("hr_average_view",false);
        chartHeader(panel,"Easy effort",()->{
            LinearLayout body=section();RadioGroup view=chartChoices(body,"Measure",new String[]{"Time below HR ceiling (%)","Average heart rate (bpm)"},average?1:0);
            bottomSheet("Easy effort settings",body,"Apply",dialog->{preferences.edit().putBoolean("hr_average_view",checkedChoice(view)==1).apply();dialog.dismiss();localRender();});
        });
        JSONArray points=dashboardData.optJSONArray("hr_points");JSONObject latest=latestPoint(points);
        if(latest!=null){addText(panel,Math.round(latest.optDouble(average?"average_hr":"hr_under_percent"))+(average?" bpm":"%"),32,ink,false,8);addText(panel,"Latest "+(average?"average HR":"time below ceiling")+" · "+latest.optString("date"),13,muted,false,2);}
        addText(panel,"Ceiling: below "+preferences.getInt("easy_hr",134)+" bpm",13,muted,false,12);
        addInteractivePlot(panel,"Easy effort",points,average?"average_hr":"hr_under_percent",average?"AVERAGE HR · BPM":"TIME BELOW CEILING · %",average?preferences.getInt("easy_hr",134):Double.NaN,false,false,ChartSeries.HEART,false);
    }
    private void chartCard(String title,String subtitle,JSONArray points,boolean trial,String[] categories){
        boolean easy=categories.length==1&&"easy".equals(categories[0]);
        LinearLayout panel=card();chartHeader(panel,title,()->paceOptions(easy));
        JSONObject latest=latestPoint(points);
        if(latest!=null){addText(panel,ScatterPlot.pace(latest.optDouble("pace"),miles)+(miles?" /mi":" /km"),32,ink,false,8);addText(panel,"Latest plotted pace · "+latest.optString("date"),13,muted,false,2);}
        addText(panel,(easy?"Shading: typical pace range":subtitle)+" · "+adjustmentLabel()+("intensity".equals(setting(easy?"easy_mode":"interval_pace_mode","observed"))?" · HR-adjusted effort":""),12,muted,false,4);
        addInteractivePlot(panel,title,points,null,null,Double.NaN,trial,easy&&!preferences.getBoolean("easy_auto_scale",true),easy?ChartSeries.EASY:ChartSeries.INTERVAL,false);
    }
    private JSONObject findRun(JSONObject point){
        if(dashboardData==null||point==null)return null;String id=point.optString("id");JSONArray runs=dashboardData.optJSONArray("runs");
        if(!id.isEmpty()&&runs!=null)for(int i=0;i<runs.length();i++)if(id.equals(runs.optJSONObject(i).optString("id")))return runs.optJSONObject(i);
        return null;
    }
    private String pointDescription(JSONObject point,String key,String label,boolean trial){
        String date=point.optString("date"),category=point.optString("category");
        if(point.optBoolean("bar"))return weekDescription(point);
        if("prediction".equals(category)||"easy_prediction".equals(category))return date+" · "+("prediction".equals(category)?"Interval estimate":"Easy estimate")+"\nEstimated 5K "+raceTime(point.optDouble("duration"))+"\nCalibrated from "+point.optInt("calibrations")+" trials. "+adjustmentLabel()+" where available.";
        JSONObject run=findRun(point);
        String heading=date+(run==null?"":" · "+run.optString("title"));
        if("hr_under_percent".equals(key)||"average_hr".equals(key)){
            String source=point.optString("hr_source").contains("average")?"Estimate from average HR":"From recorded HR samples";
            return heading+"\n"+Math.round(point.optDouble("hr_under_percent"))+"% of time below "+preferences.getInt("easy_hr",134)+" bpm\nAverage HR "+Math.round(point.optDouble("average_hr"))+" bpm · "+source;
        }
        if(key!=null)return heading+"\n"+label+": "+String.format(Locale.getDefault(),"%.1f",point.optDouble(key));
        if(trial){
            double shown=point.optDouble("duration"),raw=run!=null&&run.optJSONObject("best_5k")!=null?run.optJSONObject("best_5k").optDouble("duration"):shown;
            return heading+"\nMeasured 5K "+raceTime(raw)+(Math.abs(shown-raw)>.5?"\nShown "+raceTime(shown)+" · "+adjustmentLabel()+" where available":"");
        }
        double raw=run==null?point.optDouble("pace"):run.optDouble("pace");
        if(category.equals("short")||category.equals("medium")||category.equals("long")){
            raw=run==null?point.optDouble("work_pace"):run.optDouble("work_pace");
        }
        double shown=point.optDouble("pace");String unit=miles?" /mi":" /km";
        String mode=setting((category.equals("easy")||category.equals("easy_long"))?"easy_mode":"interval_pace_mode","observed");
        String adjustments=adjustmentLabel()+(mode.equals("intensity")?" · HR-adjusted effort":"");
        return heading+"\nRecorded pace "+ScatterPlot.pace(raw,miles)+unit+"\nShown pace "+ScatterPlot.pace(shown,miles)+unit+"\n"+adjustments+" where available";
    }
    private void showPointSheet(String title,JSONObject point,String key,String label,boolean trial){
        LinearLayout body=section();addText(body,pointDescription(point,key,label,trial),16,ink,false,12).setTextIsSelectable(true);
        boolean weekly=point.optBoolean("bar");
        if(weekly||findRun(point)!=null)button(body,weekly?"View week's sessions":"Open session",true,()->{if(pointSheet!=null)pointSheet.dismiss();if(weekly)openWeekSessions(point);else openRun(point);});
        openPointSheet(title,body);
    }
    private void openPointSheet(String title,LinearLayout body){
        if(pointSheet!=null)pointSheet.dismiss();Dialog dialog=bottomSheet(title,body,null,null);pointSheet=dialog;
        dialog.setOnDismissListener(d->{if(pointSheet==dialog)pointSheet=null;});
    }
    private void chartData(String title,String[] rows,java.util.function.IntConsumer choose){
        ArrayAdapter<String> adapter=new ArrayAdapter<String>(this,android.R.layout.simple_list_item_1,rows){
            @Override public View getView(int position,View recycled,ViewGroup parent){
                TextView view=(TextView)super.getView(position,recycled,parent);view.setSingleLine(false);view.setMaxLines(Integer.MAX_VALUE);view.setEllipsize(null);view.setTextSize(15);view.setTextColor(ink);view.setPadding(dp(20),dp(16),dp(20),dp(16));return view;
            }
        };
        new AlertDialog.Builder(this).setTitle(title+" · data").setAdapter(adapter,(d,w)->choose.accept(w)).setNegativeButton("Close",null).show();
    }
    private void addInteractivePlot(LinearLayout panel,String title,JSONArray input,String key,String label,double reference,boolean trial,boolean fixedEasy,String seriesMode,boolean expanded){
        ChartSeries series=new ChartSeries(seriesMode);
        final JSONArray points=new JSONArray();
        if(input!=null)for(int i=0;i<input.length();i++){
            JSONObject point=input.optJSONObject(i);if(point==null)continue;double value=point.optDouble(key!=null?key:trial?"duration":"pace",Double.NaN);
            if(Double.isFinite(value)&&(key!=null||value>0))points.put(point);
        }
        if(points.length()==0){chartLegend(panel,series,null);addText(panel,"No matching measurements in this date range.",15,muted,false,16);return;}
        final boolean weekly=points.optJSONObject(0).optBoolean("bar");
        String start=dashboardData.optString("start");if(weekly)start=LocalDate.parse(start).minusDays(6).toString();
        if(expanded){addText(panel,dateSpan(dashboardData.optString("start"),dashboardData.optString("end")),14,ink,false,0);addText(panel,"Drag to read · two fingers to zoom / pan · double-tap to reset",13,muted,false,8);}
        ScatterPlot plot=new ScatterPlot(this,points,start,dashboardData.optString("end"),miles,trial,fixedEasy,key,label,reference,point->showPointSheet(weekly?"Week details":"Point details",point,key,label,trial));
        plot.setSeriesVisibility(series);chartLegend(panel,series,plot::seriesVisibilityChanged);
        plot.setExplorationEnabled(expanded);int height=chartHeight(expanded?360:240)+plot.readoutHeight();panel.addView(plot,new LinearLayout.LayoutParams(-1,height));
        if(fixedEasy){int outside=0;for(int i=0;i<points.length();i++){double pace=points.optJSONObject(i).optDouble("pace")*1.609344;if(pace<420||pace>600)outside++;}if(outside>0)addText(panel,outside+" runs outside this fixed scale. Choose Fit to all measurements in chart settings to include them.",14,muted,false,4);}
        addText(panel,weekly?"Drag to read · tap a bar for week details":series.ids.length>0?"Drag to read the first enabled legend item · tap a point for details":"Drag to read · tap a point for details",12,muted,false,6);
        MaterialUi.ButtonGroup actions=new MaterialUi.ButtonGroup(this,true);actions.setPadding(0,dp(12),0,0);panel.addView(actions,new LinearLayout.LayoutParams(-1,-2));
        if(!expanded){actions.addView(actionButton("Explore chart",false,()->expandPlot(title,points,key,label,reference,trial,fixedEasy,seriesMode)));return;}
        actions.addView(actionButton("View data",false,()->{
            JSONArray visible=plot.dataPoints();
            if(visible.length()==0){new AlertDialog.Builder(this).setTitle(title+" · data").setMessage("No visible points. Turn a series on in the legend.").setPositiveButton("Close",null).show();return;}
            String[] rows=new String[visible.length()];for(int i=0;i<rows.length;i++)rows[i]=pointDescription(visible.optJSONObject(i),key,label,trial);
            chartData(title,rows,w->plot.selectPoint(visible.optJSONObject(w)));
        }));
        Button reset=actionButton("Reset zoom",false,plot::resetZoom);actions.addView(reset);reset.setVisibility(View.GONE);
        Button filter=button(panel,"Use visible dates across app",false,()->applyChartRange(plot.visibleDates()));filter.setVisibility(View.GONE);
        plot.setViewportListener(()->{boolean zoomed=plot.isZoomed();reset.setVisibility(zoomed?View.VISIBLE:View.GONE);filter.setVisibility(zoomed?View.VISIBLE:View.GONE);});
    }
    private void expandPlot(String title,JSONArray points,String key,String label,double reference,boolean trial,boolean fixedEasy,String seriesMode){
        LinearLayout panel=section();panel.setPadding(dp(16),dp(12),dp(16),dp(20));
        addInteractivePlot(panel,title,points,key,label,reference,trial,fixedEasy,seriesMode,true);showExpanded(title,panel);
    }
    private void showExpanded(String title,LinearLayout body){
        Dialog dialog=fullScreen(title,body,null);expandedChart=dialog;
        dialog.setOnDismissListener(d->{if(expandedChart==dialog)expandedChart=null;});
    }
    private void applyChartRange(String[] range){
        if(expandedChart!=null)expandedChart.dismiss();
        saveSetting("custom_start",range[0]);saveSetting("custom_end",range[1]);days=-1;preferences.edit().putInt("days",days).apply();updateChrome();loadDashboard(false);
    }
    private void weeklyCard(){
        LinearLayout panel=card();
        String[] keys={"run_miles","total_minutes","run_minutes","training_load","interval_percent"};
        String[] labels={"Run distance","Total time","Run time","Garmin training load","Active interval %"};
        String current=setting("weekly_metric","run_miles");int selected=0;for(int i=0;i<keys.length;i++)if(keys[i].equals(current))selected=i;
        final String metric=keys[selected];String label=labels[selected];
        final int initial=selected;
        chartHeader(panel,"Weekly training",()->{
            LinearLayout body=section();RadioGroup view=chartChoices(body,"Measure",labels,initial);
            bottomSheet("Weekly training settings",body,"Apply",dialog->{saveSetting("weekly_metric",keys[checkedChoice(view)]);dialog.dismiss();loadDashboard(false);});
        });
        JSONArray points=new JSONArray(),weeks=dashboardData.optJSONArray("weeks");
        if(weeks!=null)for(int i=0;i<weeks.length();i++){
            JSONObject week=weeks.optJSONObject(i);double value=week.optDouble(metric,0);
            if(metric.endsWith("minutes"))value/=60;if(metric.equals("run_miles")&&!miles)value*=1.609344;
            try{points.put(new JSONObject().put("date",week.optString("date")).put("value",value).put("bar",true).put("metric",metric).put("color",palette.primary));}catch(Exception ignored){}
        }
        String axis=metric.endsWith("minutes")?"HOURS":metric.equals("run_miles")?"RUN DISTANCE · "+(miles?"MI":"KM"):metric.equals("interval_percent")?"ACTIVE INTERVAL %":"GARMIN LOAD";
        JSONObject latest=latestPoint(points);
        if(latest!=null){addText(panel,String.format(Locale.getDefault(),"%.1f",latest.optDouble("value"))+(metric.endsWith("minutes")?" h":metric.equals("run_miles")?(miles?" mi":" km"):metric.equals("interval_percent")?"%":""),32,ink,false,8);addText(panel,label+" · week of "+latest.optString("date"),13,muted,false,2);}
        addText(panel,"Calendar-week totals · current week may be incomplete",12,muted,false,12);
        if(dashboardData.optString("start").compareTo("2026-03-30")<0&&dashboardData.optString("end").compareTo("2025-12-11")>=0)addText(panel,"Amber shading: injury / rebuild period",12,muted,false,4);
        addInteractivePlot(panel,"Weekly training",points,"value",axis,Double.NaN,false,false,ChartSeries.NONE,false);
    }
    private String weekDescription(JSONObject point){
        String day=point.optString("date");JSONObject week=null;JSONArray weeks=dashboardData.optJSONArray("weeks");
        if(weeks!=null)for(int i=0;i<weeks.length();i++)if(day.equals(weeks.optJSONObject(i).optString("date")))week=weeks.optJSONObject(i);
        if(week==null)return day;
        StringBuilder preview=new StringBuilder();JSONArray runs=dashboardData.optJSONArray("runs");int shown=0;String finalDay=LocalDate.parse(day).plusDays(6).toString();
        if(runs!=null)for(int i=0;i<runs.length()&&shown<3;i++){JSONObject run=runs.optJSONObject(i);if(day.compareTo(run.optString("date"))<=0&&finalDay.compareTo(run.optString("date"))>=0){preview.append("\n• ").append(run.optString("title"));shown++;}}
        double unit=miles?1:1.609344;
        return dateSpan(day,LocalDate.parse(day).plusDays(6).toString())+"\n"+String.format(Locale.getDefault(),"%.1f %s · %.1f h total · %.1f h running",week.optDouble("run_miles")*unit,miles?"mi":"km",week.optDouble("total_minutes")/60,week.optDouble("run_minutes")/60)+"\nGarmin load "+Math.round(week.optDouble("training_load"))+" · "+Math.round(week.optDouble("interval_percent"))+"% active intervals\n"+week.optInt("sessions")+" sessions"+(shown>0?"\nIn the current date range:"+preview.toString():"");
    }
    private void openWeekSessions(JSONObject point){
        String first=point.optString("date"),end=LocalDate.parse(first).plusDays(6).toString();
        final String last=end.compareTo(LocalDate.now().toString())>0?LocalDate.now().toString():end;
        execute("Opening saved week's sessions…",()->{JSONObject state=settings();state.put("custom_start",first);state.put("custom_end",last);return invoke("cached_dashboard",LocalDate.now().toString(),-1,state.toString());},result->{
            JSONArray runs=result.optJSONArray("runs");if(runs==null||runs.length()==0){message.setText("No sessions recorded in this week.");return;}
            String[] names=new String[runs.length()];for(int i=0;i<names.length;i++){JSONObject run=runs.optJSONObject(i);names[i]=run.optString("date")+" · "+run.optString("title")+"\n"+sessionMetrics(run);}
            new AlertDialog.Builder(this).setTitle("Week's sessions").setItems(names,(d,w)->showRun(runs.optJSONObject(w))).setNegativeButton("Close",null).show();
        });
    }
    private void recoveryCard(){
        LinearLayout panel=card();String metric=preferences.getString("recovery_view","all");
        String[] options={"All three metrics","Sleep","Resting heart rate","HRV"},values={"all","sleep_hours","resting_hr","hrv"};int index=0;for(int i=0;i<values.length;i++)if(values[i].equals(metric))index=i;final int chosen=index;
        chartHeader(panel,"Weekly recovery",()->{
            LinearLayout body=section();RadioGroup view=chartChoices(body,"Show",options,chosen);
            bottomSheet("Recovery settings",body,"Apply",dialog->{preferences.edit().putString("recovery_view",values[checkedChoice(view)]).apply();dialog.dismiss();localRender();});
        });
        JSONArray weeks=dashboardData.optJSONArray("weeks");if(weeks==null||weeks.length()==0){addText(panel,"No recovery measurements in this date range.",15,muted,false,12);return;}
        String[] keys={"sleep_hours","resting_hr","hrv"},names={"Sleep","Resting HR","HRV"},units={" h"," bpm"," ms"};
        MaterialUi.ButtonGroup summaries=new MaterialUi.ButtonGroup(this,true);summaries.setPadding(0,dp(12),0,dp(12));
        for(int k=0;k<keys.length;k++){
            if(!metric.equals("all")&&!metric.equals(keys[k]))continue;
            JSONObject latest=null;for(int i=weeks.length()-1;i>=0;i--)if(Double.isFinite(weeks.optJSONObject(i).optDouble(keys[k],Double.NaN))){latest=weeks.optJSONObject(i);break;}
            LinearLayout tile=section();tile.setPadding(dp(8),dp(8),dp(8),dp(8));tile.setBackground(shape(palette.high,12));
            addText(tile,names[k],12,muted,true,0);addText(tile,latest==null?"—":String.format(Locale.getDefault(),k==0?"%.1f":"%.0f",latest.optDouble(keys[k]))+units[k],22,ink,false,4);
            addText(tile,latest==null?"No measurements":latest.optInt(keys[k]+"_days")+" days",12,muted,false,4);
            if(latest!=null)addText(tile,"Week of\n"+latest.optString("date"),11,muted,false,4);summaries.addView(tile);
        }
        panel.addView(summaries,new LinearLayout.LayoutParams(-1,-2));
        addText(panel,"Weekly averages · gaps mean missing measurements",12,muted,false,4);addRecoveryPlot(panel,weeks,metric,false);
    }
    private void addRecoveryPlot(LinearLayout panel,JSONArray weeks,String metric,boolean expanded){
        if(expanded){addText(panel,dateSpan(dashboardData.optString("start"),dashboardData.optString("end")),14,ink,false,0);addText(panel,"Drag to read · two fingers to zoom / pan dates · double-tap to reset",13,muted,false,8);}
        RecoveryPlot plot=new RecoveryPlot(this,weeks,metric,point->{LinearLayout body=section();addText(body,recoveryDescription(point),16,ink,false,12).setTextIsSelectable(true);openPointSheet("Recovery details",body);});
        plot.setExplorationEnabled(expanded);panel.addView(plot,new LinearLayout.LayoutParams(-1,chartHeight(metric.equals("all")?420:expanded?360:240)+plot.readoutHeight()));
        addText(panel,"Drag across a metric to read · tap for details and measured days",12,muted,false,6);
        MaterialUi.ButtonGroup actions=new MaterialUi.ButtonGroup(this,true);actions.setPadding(0,dp(12),0,0);panel.addView(actions,new LinearLayout.LayoutParams(-1,-2));
        if(!expanded){actions.addView(actionButton("Explore chart",false,()->{LinearLayout body=section();body.setPadding(dp(16),dp(12),dp(16),dp(16));addRecoveryPlot(body,weeks,metric,true);showExpanded("Weekly recovery",body);}));return;}
        actions.addView(actionButton("View data",false,()->{JSONArray rows=plot.dataPoints();if(rows.length()==0){new AlertDialog.Builder(this).setTitle("Recovery data").setMessage("No saved measurements in this date range.").setPositiveButton("Close",null).show();return;}String[] labels=new String[rows.length()];for(int i=0;i<labels.length;i++)labels[i]=recoveryDescription(rows.optJSONObject(i));chartData("Recovery",labels,w->plot.selectPoint(rows.optJSONObject(w)));}));
        Button reset=actionButton("Reset zoom",false,plot::resetZoom);actions.addView(reset);reset.setVisibility(View.GONE);
        Button filter=button(panel,"Use visible dates across app",false,()->applyChartRange(plot.visibleDates()));filter.setVisibility(View.GONE);
        plot.setViewportListener(()->{reset.setVisibility(plot.isZoomed()?View.VISIBLE:View.GONE);filter.setVisibility(plot.isZoomed()?View.VISIBLE:View.GONE);});
    }
    private String recoveryDescription(JSONObject point){return "Week of "+point.optString("date")+"\n"+point.optString("label")+": "+point.optString("formatted")+"\n"+point.optInt("days")+" measured days";}
    private void renderKpis(JSONObject summary){
        JSONObject latest=summary.optJSONObject("latest_trial"),best=summary.optJSONObject("best_trial");
        LinearLayout trial=card();LinearLayout.LayoutParams heroLp=(LinearLayout.LayoutParams)trial.getLayoutParams();heroLp.topMargin=dp(20);trial.setLayoutParams(heroLp);
        trial.setBackground(shape(palette.primaryContainer,24));
        addText(trial,"Latest measured 5K",14,palette.onPrimaryContainer,true,0);
        JSONObject effort=latest==null?null:latest.optJSONObject("best_5k");
        addText(trial,effort==null?"—":raceTime(effort.optDouble("duration")),40,palette.onPrimaryContainer,false,8);
        addText(trial,latest==null?"A recorded 5K trial will appear here":latest.optString("date")+" · recorded fastest 5K",13,palette.onPrimaryContainer,false,6);
        JSONObject bestEffort=best==null?null:best.optJSONObject("best_5k");
        if(bestEffort!=null)addText(trial,"Best in range · "+raceTime(bestEffort.optDouble("duration"))+" · "+best.optString("date"),13,palette.onPrimaryContainer,true,12);
        String distance=miles?"mi":"km";double multiplier=miles?1:1.609344;
        LinearLayout row=new LinearLayout(this);row.setOrientation(getResources().getConfiguration().fontScale>1.3f?LinearLayout.VERTICAL:LinearLayout.HORIZONTAL);content.addView(row);
        summaryTile(row,"Run volume",String.format(Locale.getDefault(),"%.1f %s",summary.optDouble("run_miles")*multiplier,distance),String.format(Locale.getDefault(),"%.1f %s/week · last 4 weeks",summary.optDouble("last_four_miles",0)*multiplier,distance));
        summaryTile(row,"Easy effort",summary.isNull("easy_percent")?"—":Math.round(summary.optDouble("easy_percent"))+"%","time below "+preferences.getInt("easy_hr",134)+" bpm");
        addText(content,summary.optInt("interval_count")+" interval sessions · "+String.format(Locale.getDefault(),"%.1f h cross-training",summary.optDouble("cross_hours")),13,muted,false,0);
    }
    private void summaryTile(LinearLayout row,String title,String value,String note){
        LinearLayout tile=section();tile.setPadding(dp(16),dp(16),dp(16),dp(16));tile.setBackground(panelShape());
        addText(tile,title,13,muted,true,0);addText(tile,value,26,ink,false,8);addText(tile,note,12,muted,false,6);
        boolean vertical=row.getOrientation()==LinearLayout.VERTICAL;
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(vertical?-1:0,-2,vertical?0:1);if(row.getChildCount()>0&&!vertical)lp.leftMargin=dp(8);lp.bottomMargin=dp(12);row.addView(tile,lp);
    }
    private boolean intervalSession(JSONObject run){
        String category=run.optString("category");return category.equals("short")||category.equals("medium")||category.equals("long");
    }
    private boolean sessionAdjusted(JSONObject run){return run.optBoolean("is_run",true)&&(adjusted("adjust_elevation")||adjusted("adjust_temperature"));}
    private double sessionPace(JSONObject run,boolean work){
        double raw=run.optDouble(work?"work_pace":"pace",Double.NaN);
        return sessionAdjusted(run)?run.optDouble(work?"display_work_pace":"display_overall_pace",raw):raw;
    }
    private String sessionPaceLabel(JSONObject run,boolean work){return (sessionAdjusted(run)?"Adj ":"")+(work?"work pace":"pace");}
    private String paceValue(double value){return Double.isFinite(value)&&value>0?ScatterPlot.pace(value,miles):"—";}
    private String hrValue(double value){return Double.isFinite(value)&&value>0?Long.toString(Math.round(value)):"—";}
    private boolean hasWorkMetrics(JSONObject run){return intervalSession(run)&&(Double.isFinite(run.optDouble("work_pace",Double.NaN))||Double.isFinite(run.optDouble("work_hr",Double.NaN))||Double.isFinite(run.optDouble("work_distance",Double.NaN))||Double.isFinite(run.optDouble("work_duration",Double.NaN)));}
    private String sessionDistanceValue(double value){return Double.isFinite(value)&&value>0?String.format(Locale.getDefault(),"%.2f",value/(miles?1609.344:1000)):"—";}
    private String sessionTimeValue(double value){return Double.isFinite(value)&&value>0?raceTime(value):"—";}
    private String sessionSummary(JSONObject run){
        return distanceText(run)+" · "+sessionPaceLabel(run,false)+" "+paceValue(sessionPace(run,false))+(miles?" /mi":" /km")
            +(run.isNull("duration")?"":" · "+raceTime(run.optDouble("duration")))+" · "+hrValue(run.optDouble("average_hr",Double.NaN))+" bpm average";
    }
    private String sessionConditions(JSONObject run){
        java.util.ArrayList<String> details=new java.util.ArrayList<>();
        double gain=run.optDouble("elevation_gain",Double.NaN),loss=run.optDouble("elevation_loss",Double.NaN);
        if(Double.isFinite(gain)&&Double.isFinite(loss))details.add("+"+Math.round(Math.abs(gain)*3.28084)+" / −"+Math.round(Math.abs(loss)*3.28084)+" ft");
        else if(Double.isFinite(gain))details.add("+"+Math.round(Math.abs(gain)*3.28084)+" ft");
        else if(Double.isFinite(loss))details.add("−"+Math.round(Math.abs(loss)*3.28084)+" ft");
        double below=run.optDouble("hr_under_percent",Double.NaN);if(Double.isFinite(below))details.add("Easy HR "+Math.round(below)+"%");
        JSONObject weather=run.optJSONObject("weather");double temperature=weather==null?Double.NaN:weather.optDouble("temperatureF",Double.NaN);
        if(Double.isFinite(temperature))details.add(Math.round(temperature)+" °F");
        return String.join(" · ",details);
    }
    private String sessionMetrics(JSONObject run){
        String result=sessionSummary(run);
        if(hasWorkMetrics(run))result+="\nWork intervals: "+sessionDistanceValue(run.optDouble("work_distance",Double.NaN))+(miles?" mi":" km")+" · "+sessionPaceLabel(run,true)+" "+paceValue(sessionPace(run,true))+(miles?" /mi":" /km")+" · "+sessionTimeValue(run.optDouble("work_duration",Double.NaN))+" work time · "+hrValue(run.optDouble("work_hr",Double.NaN))+" bpm work average";
        String conditions=sessionConditions(run);if(!conditions.isEmpty())result+="\n"+conditions;
        JSONObject effort=run.optJSONObject("best_5k");if(effort!=null)result+="\nMeasured 5K "+raceTime(effort.optDouble("duration"));
        return result;
    }
    private void sessionMetric(MaterialUi.MetricGroup parent,String label,String value,boolean secondary){
        LinearLayout column=section();column.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);
        TextView caption=text(label,11,muted,false);caption.setLineSpacing(0,1);caption.setIncludeFontPadding(false);column.addView(caption,new LinearLayout.LayoutParams(-1,-2));
        TextView number=text(value,secondary?16:18,secondary?palette.primary:ink,true);number.setLineSpacing(0,1);number.setIncludeFontPadding(false);
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(2);column.addView(number,lp);parent.addView(column);
    }
    private void sessionWorkMetric(MaterialUi.MetricGroup parent,String value){
        TextView view=text(value,16,palette.primary,true);view.setLineSpacing(0,1);view.setIncludeFontPadding(false);view.setPadding(0,dp(2),0,dp(2));
        view.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);parent.addView(view);
    }
    private void sessionCard(LinearLayout parent,JSONObject run){
        LinearLayout row=section();row.setPadding(dp(12),dp(10),dp(12),dp(10));row.setBackground(MaterialUi.ripple(this,palette.container,16,palette.primary));row.setMinimumHeight(dp(48));row.setFocusable(true);
        String category=run.optString("category"),unit=miles?" /mi":" /km";
        JSONObject effort=run.optJSONObject("best_5k");
        TextView type=addText(row,ScatterPlot.label(category)+" · "+sessionCardDate(run.optString("date"))+(effort==null?"":" · 5K "+raceTime(effort.optDouble("duration"))),11,muted,true,0);
        type.setMaxLines(2);type.setEllipsize(TextUtils.TruncateAt.END);
        GradientDrawable marker=shape(palette.chart(ScatterPlot.color(category)),4);marker.setBounds(0,0,dp(8),dp(8));type.setCompoundDrawables(marker,null,null,null);type.setCompoundDrawablePadding(dp(5));
        MaterialUi.MetricGroup metrics=new MaterialUi.MetricGroup(this);metrics.setPadding(0,dp(5),0,0);
        double distance=run.optDouble("distance",Double.NaN),duration=run.optDouble("duration",Double.NaN);
        sessionMetric(metrics,miles?"Distance mi":"Distance km",sessionDistanceValue(distance),false);
        sessionMetric(metrics,sessionAdjusted(run)?"Adj pace"+unit:"Pace"+unit,paceValue(sessionPace(run,false)),false);
        sessionMetric(metrics,"Time",sessionTimeValue(duration),false);
        sessionMetric(metrics,"Avg HR",hrValue(run.optDouble("average_hr",Double.NaN)),false);
        if(hasWorkMetrics(run)){
            // Both rows share distance, pace, time and HR columns, including when wrapped.
            metrics.shadeFrom(4,palette.high);
            sessionWorkMetric(metrics,sessionDistanceValue(run.optDouble("work_distance",Double.NaN)));
            sessionWorkMetric(metrics,paceValue(sessionPace(run,true)));
            sessionWorkMetric(metrics,sessionTimeValue(run.optDouble("work_duration",Double.NaN)));
            sessionWorkMetric(metrics,hrValue(run.optDouble("work_hr",Double.NaN)));
        }
        row.addView(metrics,new LinearLayout.LayoutParams(-1,-2));
        LinearLayout footer=new LinearLayout(this);footer.setGravity(Gravity.CENTER_VERTICAL);
        String conditions=sessionConditions(run);if(!conditions.isEmpty())footer.addView(text(conditions+" · ",12,muted,false),new LinearLayout.LayoutParams(-2,-2));
        TextView name=text(run.optString("title"),12,muted,false);name.setMaxLines(1);name.setEllipsize(TextUtils.TruncateAt.END);
        footer.addView(name,new LinearLayout.LayoutParams(0,-2,1));
        LinearLayout.LayoutParams footerLp=new LinearLayout.LayoutParams(-1,-2);footerLp.topMargin=dp(4);row.addView(footer,footerLp);
        if(needsReview(run))addText(row,"Needs review",11,palette.error,false,2);
        row.setContentDescription(run.optString("title")+", "+run.optString("date")+", "+ScatterPlot.label(category)+", "+sessionMetrics(run)+(needsReview(run)?". Needs review":"")+". Open session details.");
        row.setOnClickListener(v->{if(!busy)showRun(run);});LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(6);parent.addView(row,lp);
    }
    private static final String[] ROUTE_KINDS={"easy","easy_long","intervals","short","medium","long"};
    private static final String[] ROUTE_KIND_LABELS={"Easy","Easy long","Intervals","Short","Medium","Long"};
    private String routeKindLabel(String kind){for(int i=0;i<ROUTE_KINDS.length;i++)if(ROUTE_KINDS[i].equals(kind))return ROUTE_KIND_LABELS[i];return "Easy";}
    private void renderRouteProfile(){
        LinearLayout routes=card();addText(routes,"Routes",22,ink,false,0);
        addText(routes,"One reference per route. Choose out-and-back, loop or one-way, and Road or Trail. Every workout uses its own portion of the elevation profile.",13,muted,false,8);
        button(routes,"Manage routes",false,this::showTrainingRouteManager);
        LinearLayout panel=card();addText(panel,"Workouts",22,ink,false,0);
        LinearLayout summary=section();panel.addView(summary);renderWorkoutSummary(summary);
        button(panel,"Edit workouts",false,()->showWorkoutEditor(()->renderWorkoutSummary(summary)));
    }
    private String workoutMinutes(double value){return java.math.BigDecimal.valueOf(value).stripTrailingZeros().toPlainString();}
    private void renderWorkoutSummary(LinearLayout summary){
        summary.removeAllViews();JSONObject state;
        try{state=settings();}catch(Exception error){addText(summary,"Couldn't read saved workouts.",13,palette.error,false,8);return;}
        JSONObject definitions=state.optJSONObject("workout_definitions");
        addText(summary,"Easy "+setting("target_easy_minutes","45")+" min · Easy long "+setting("target_easy_long_minutes","80")+" min",14,ink,false,8);
        for(String kind:new String[]{"short","medium","long"}){
            JSONObject definition=definitions==null?null:definitions.optJSONObject(kind);if(definition==null)definition=new JSONObject();
            int reps=definition.optInt("reps",kind.equals("short")?10:kind.equals("medium")?6:3);
            double work=definition.optDouble("work",kind.equals("short")?3:kind.equals("medium")?5:10);
            addText(summary,routeKindLabel(kind)+" · "+reps+" × "+workoutMinutes(work)+" min · "+workoutMinutes(definition.optDouble("warmup",10))+" / "+workoutMinutes(definition.optDouble("cooldown",10))+" min",14,ink,false,6);
        }
        addText(summary,"Intervals: reps × work · warm-up / cooldown",12,muted,false,4);
        double pace=state.optDouble("target_walking_pace",1200/1.609344);
        addText(summary,"Recovery · 1 min walk after every rep · "+ScatterPlot.pace(pace,miles)+(miles?" /mi":" /km"),13,muted,false,8);
    }
    private void showWorkoutEditor(Runnable changed){
        LinearLayout body=section();TextView status=addText(body,"Changes save automatically",12,muted,false,0);
        LinearLayout fields=section();body.addView(fields);
        Dialog sheet=bottomSheet("Edit workouts",body,"Done",Dialog::dismiss);
        Runnable[] redraw={null};redraw[0]=()->{fields.removeAllViews();renderWorkoutEditor(fields,sheet,status,redraw[0]);};
        sheet.setOnDismissListener(dialog->changed.run());redraw[0].run();
    }
    private void renderWorkoutEditor(LinearLayout panel,Dialog owner,TextView loadStatus,Runnable redraw){
        addText(panel,"Warm-up and cooldown use the selected surface’s 128 bpm easy pace. Every repetition is followed by a one-minute walk, including the last.",13,muted,false,8);
        for(String kind:new String[]{"easy","easy_long"}){
            String key=kind.equals("easy")?"target_easy_minutes":"target_easy_long_minutes";
            EditText minutes=input(panel,routeKindLabel(kind)+" · minutes",InputType.TYPE_CLASS_NUMBER);minutes.setText(setting(key,kind.equals("easy")?"45":"80"));
            minutes.addTextChangedListener(new TextWatcher(){
                public void beforeTextChanged(CharSequence text,int start,int count,int after){}
                public void onTextChanged(CharSequence text,int start,int before,int count){
                    try{int n=Integer.parseInt(text.toString().trim());if(n<5||n>360)throw new NumberFormatException();minutes.setError(null);saveSetting(key,n);profileDirty=true;preferences.edit().remove("workout_source_"+kind).apply();}
                    catch(NumberFormatException error){minutes.setError("Use 5–360 minutes");}
                }
                public void afterTextChanged(Editable text){}
            });
            smallButton(panel,"Use latest "+routeKindLabel(kind)+" session",()->useLatestWorkout(kind,owner,loadStatus,panel,redraw));
            String source=preferences.getString("workout_source_"+kind,"");if(!source.isEmpty())addText(panel,source,11,muted,false,2);
        }
        EditText walking=input(panel,"Walking pace · min/"+(miles?"mi":"km"),InputType.TYPE_CLASS_TEXT);walking.setHint(miles?"20:00":"12:26");
        double walk=1200/1.609344;try{walk=Double.parseDouble(setting("target_walking_pace",Double.toString(walk)));}catch(Exception ignored){}
        walking.setText(ScatterPlot.pace(walk,miles));
        walking.addTextChangedListener(new TextWatcher(){
            public void beforeTextChanged(CharSequence text,int start,int count,int after){}
            public void onTextChanged(CharSequence text,int start,int before,int count){
                try{String[] parts=text.toString().trim().split(":",-1);if(parts.length!=2)throw new NumberFormatException();int min=Integer.parseInt(parts[0]),sec=Integer.parseInt(parts[1]);if(min<0||sec<0||sec>=60)throw new NumberFormatException();double pace=(min*60+sec)/(miles?1.609344:1);if(pace<240||pace>2400)throw new NumberFormatException();walking.setError(null);saveSetting("target_walking_pace",pace);preferences.edit().remove("workout_source_walking").apply();profileDirty=true;}
                catch(NumberFormatException error){walking.setError("Use mm:ss from "+(miles?"6:27–64:22 /mi":"4:00–40:00 /km"));}
            }
            public void afterTextChanged(Editable text){}
        });
        smallButton(panel,"Use walking recoveries from latest interval session",()->useLatestWorkout("walking",owner,loadStatus,panel,redraw));
        String walkingSource=preferences.getString("workout_source_walking","");if(!walkingSource.isEmpty())addText(panel,walkingSource,11,muted,false,2);
        for(String kind:new String[]{"short","medium","long"})renderIntervalWorkoutEditor(panel,kind,()->useLatestWorkout(kind,owner,loadStatus,panel,redraw));
    }
    private void renderIntervalWorkoutEditor(LinearLayout parent,String kind,Runnable useLatest){
        LinearLayout panel=section();panel.setPadding(dp(12),dp(12),dp(12),dp(12));panel.setBackground(shape(palette.high,16));
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(14);parent.addView(panel,lp);addText(panel,routeKindLabel(kind),16,ink,true,0);
        JSONObject definition=null;try{definition=settings().optJSONObject("workout_definitions");if(definition!=null)definition=definition.optJSONObject(kind);}catch(Exception ignored){}
        String[] keys={"warmup","reps","work","cooldown"},labels={"Warm-up min","Repetitions","Work min","Cooldown min"};
        double[] defaults={10,kind.equals("short")?10:kind.equals("medium")?6:3,kind.equals("short")?3:kind.equals("medium")?5:10,10};
        EditText[] fields=new EditText[4];MaterialUi.MetricGroup grid=new MaterialUi.MetricGroup(this);
        for(int i=0;i<4;i++){LinearLayout column=section();fields[i]=input(column,labels[i],InputType.TYPE_CLASS_NUMBER|(i==1?0:InputType.TYPE_NUMBER_FLAG_DECIMAL));fields[i].setMinWidth(dp(64));double value=definition==null?defaults[i]:definition.optDouble(keys[i],defaults[i]);fields[i].setText(i==1?Integer.toString((int)value):Double.toString(value));grid.addView(column);}
        panel.addView(grid,new LinearLayout.LayoutParams(-1,-2));TextView status=addText(panel,preferences.getString("workout_source_"+kind,"Edits save automatically · 1 min walking after every rep"),11,muted,false,4);
        for(EditText field:fields)field.addTextChangedListener(new TextWatcher(){
            public void beforeTextChanged(CharSequence text,int start,int count,int after){}
            public void onTextChanged(CharSequence text,int start,int before,int count){
                try{double[] values=new double[4];for(int j=0;j<4;j++){values[j]=Double.parseDouble(fields[j].getText().toString());if(!Double.isFinite(values[j]))throw new NumberFormatException();}
                    if(values[0]<0||values[0]>120||values[3]<0||values[3]>120||values[1]<1||values[1]>40||values[1]!=Math.rint(values[1])||values[2]<.5||values[2]>60||values[0]+values[3]+values[1]*(values[2]+1)>360)throw new NumberFormatException();
                    JSONObject state=settings(),definitions=state.optJSONObject("workout_definitions");if(definitions==null)definitions=new JSONObject();JSONObject saved=new JSONObject();for(int j=0;j<4;j++)saved.put(keys[j],values[j]);definitions.put(kind,saved);state.put("workout_definitions",definitions);
                    preferences.edit().putString("settings",state.toString()).remove("workout_source_"+kind).apply();profileDirty=true;status.setText("Saved · 1 min walking after every rep");
                }catch(Exception error){status.setText("Use 0–120 min warm-up/cooldown, 1–40 reps, 0.5–60 min work; total at most 6 hours.");}
            }
            public void afterTextChanged(Editable text){}
        });
        smallButton(panel,"Use latest "+routeKindLabel(kind)+" session",useLatest);
    }
    private void useLatestWorkout(String kind,Dialog owner,TextView status,LinearLayout controls,Runnable redraw){
        trainingRouteRequest(owner,status,controls,()->invoke("workout_latest",kind,LocalDate.now().toString(),settings().toString()),result->{
            try{JSONObject state=settings();if(kind.equals("easy")||kind.equals("easy_long"))state.put(kind.equals("easy")?"target_easy_minutes":"target_easy_long_minutes",result.getInt("minutes"));
                else if(!kind.equals("walking")){JSONObject definitions=state.optJSONObject("workout_definitions");if(definitions==null)definitions=new JSONObject();definitions.put(kind,result.getJSONObject("definition"));state.put("workout_definitions",definitions);}
                if(!result.isNull("walking_pace"))state.put("target_walking_pace",result.getDouble("walking_pace"));
                JSONObject source=result.getJSONObject("source");preferences.edit().putString("settings",state.toString()).putString("workout_source_"+kind,"From "+source.optString("date")+" · "+source.optString("title")).apply();profileDirty=true;redraw.run();
                status.setText("Workout loaded from "+source.optString("date")+(result.isNull("walking_pace")?"":" · walking pace updated from recovery laps"));
            }catch(Exception error){status.setText("Couldn't save this workout definition.");}
        });
    }
    private void trainingRouteRequest(Dialog owner,TextView status,View controls,Work work,Result done){
        status.setText("Loading…");enable(controls,false);
        BackendRuntime.WORKER.execute(()->{
            JSONObject result=null;try{result=work.run();}catch(Exception ignored){}
            final JSONObject data=result;
            runOnUiThread(()->{
                if(isDestroyed()||!owner.isShowing())return;enable(controls,true);
                if(data==null||!data.optBoolean("ok")){status.setText(data==null?"Couldn't load saved data. Try again.":data.optString("error","Couldn't load saved data. Try again."));return;}
                status.setText("");if(data.has("routes"))savedTrainingRoutes=data.optJSONArray("routes");done.accept(data);
            });
        });
    }
    private JSONObject trainingRoute(String id){for(int i=0;i<savedTrainingRoutes.length();i++){JSONObject route=savedTrainingRoutes.optJSONObject(i);if(route!=null&&id.equals(route.optString("id")))return route;}return null;}
    private void showTrainingRouteManager(){
        LinearLayout body=section();body.setPadding(dp(20),dp(8),dp(20),dp(20));
        TextView status=addText(body,"Loading routes…",13,muted,false,0);LinearLayout list=section();body.addView(list);
        Dialog page=fullScreen("Routes",body,null);Runnable[] reload={null};
        reload[0]=()->trainingRouteRequest(page,status,list,()->invoke("route_book",settings().toString()),result->{
            list.removeAllViews();for(int i=0;i<savedTrainingRoutes.length();i++){
                JSONObject route=savedTrainingRoutes.optJSONObject(i);String id=route.optString("id");
                button(list,route.optString("name"),false,()->showTrainingRouteConfig(id));
                addText(list,routeShapeLabel(route.optString("shape"))+" · "+route.optString("surface")+(route.isNull("reference")?" · Choose reference":" · Reference selected"),12,muted,false,2);
            }
        });
        button(body,"Reload routes",false,()->reload[0].run());reload[0].run();
    }
    private void showTrainingRouteConfig(String routeId){
        LinearLayout body=section();body.setPadding(dp(20),dp(8),dp(20),dp(20));
        TextView status=addText(body,"",13,muted,false,0);LinearLayout entries=section();body.addView(entries);
        Dialog page=fullScreen("Route configuration",body,null);
        Runnable redraw=()->renderTrainingRouteConfig(page,status,entries,routeId);
        trainingRouteRequest(page,status,entries,()->invoke("route_book",settings().toString()),result->redraw.run());
        page.setOnDismissListener(dialog->refreshActiveTrainingRoute());
    }
    private String referenceSummary(JSONObject ref){
        String distance=String.format(Locale.getDefault(),"%.2f %s",ref.optDouble("distance")/(miles?1609.344:1000),miles?"mi":"km");
        return sessionCardDate(ref.optString("date"))+" · "+distance+" · "+raceTime(ref.optDouble("duration"))+String.format(Locale.getDefault()," · +%.0f / −%.0f ft",ref.optDouble("gain"),ref.optDouble("loss"));
    }
    private String routeShapeLabel(String shape){return shape.equals("loop")?"Loop":shape.equals("one_way")?"One-way":"Out-and-back";}
    private void changeRouteConfiguration(Dialog page,TextView status,LinearLayout entries,String id,JSONObject patch){
        trainingRouteRequest(page,status,entries,()->invoke("route_configure",id,patch.toString(),settings().toString()),result->renderTrainingRouteConfig(page,status,entries,id));
    }
    private JSONObject routePatch(String key,Object value){JSONObject result=new JSONObject();try{result.put(key,value);}catch(Exception ignored){}return result;}
    private void renderTrainingRouteConfig(Dialog page,TextView status,LinearLayout entries,String routeId){
        entries.removeAllViews();JSONObject route=trainingRoute(routeId);if(route==null){status.setText("Route not found.");return;}
        addText(entries,route.optString("name"),22,ink,true,8);
        smallButton(entries,"Rename",()->{EditText name=new EditText(this);name.setText(route.optString("name"));new AlertDialog.Builder(this).setTitle("Route name").setView(name).setNegativeButton("Cancel",null).setPositiveButton("Save",(d,w)->changeRouteConfiguration(page,status,entries,routeId,routePatch("name",name.getText().toString()))).show();});
        addText(entries,"Route shape",14,muted,true,12);String[] shapes={"out_back","loop","one_way"};int selected=route.optString("shape").equals("loop")?1:route.optString("shape").equals("one_way")?2:0;
        segmented(entries,new String[]{"Out-and-back","Loop","One-way"},selected,which->{if(which!=selected)changeRouteConfiguration(page,status,entries,routeId,routePatch("shape",shapes[which]));});
        addText(entries,"Surface · chooses the 128 bpm easy-pace model",14,muted,true,12);
        segmented(entries,new String[]{"Road","Trail"},route.optString("surface").equals("trail")?1:0,which->{String surface=which==0?"road":"trail";if(!surface.equals(route.optString("surface")))changeRouteConfiguration(page,status,entries,routeId,routePatch("surface",surface));});
        Switch reverse=new Switch(this);reverse.setText("Reverse reference direction");reverse.setTextColor(ink);reverse.setMinHeight(dp(48));reverse.setChecked(route.optBoolean("reverse"));entries.addView(reverse);reverse.setOnCheckedChangeListener((button,checked)->changeRouteConfiguration(page,status,entries,routeId,routePatch("reverse",checked)));
        JSONObject ref=route.optJSONObject("reference");
        if(ref!=null){
            addText(entries,ref.optString("title"),16,ink,true,12);addText(entries,referenceSummary(ref),12,muted,false,4);
            if(ref.optBoolean("stale"))addText(entries,"The reference session changed. Choose it again.",12,palette.error,false,4);
            RouteView preview=new RouteView(this,palette);if(preview.setRoute(ref.optJSONObject("outline")))entries.addView(preview,new LinearLayout.LayoutParams(-1,dp(150)));
            if(!route.optBoolean("profile_ready"))addText(entries,"Selecting this route will read the reference’s elevation profile once. Choose another reference if it has no recorded altitude.",12,muted,false,6);
            if(route.optBoolean("profile_ready")&&!route.optString("shape").equals("one_way")){
                String label=route.optString("shape").equals("loop")?"Loop length":"Reference turnaround · distance from start";
                EditText extent=input(entries,label+" · "+(miles?"mi":"km"),InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_DECIMAL);
                extent.setText(String.format(Locale.ROOT,"%.3f",route.optDouble("extent")/(miles?1609.344:1000)));
                smallButton(entries,"Save "+(route.optString("shape").equals("loop")?"loop length":"turnaround"),()->{
                    try{double distance=Double.parseDouble(extent.getText().toString())*(miles?1609.344:1000);if(!Double.isFinite(distance)||distance<100||distance>ref.optDouble("distance")+1)throw new NumberFormatException();changeRouteConfiguration(page,status,entries,routeId,routePatch("extent",Math.min(distance,ref.optDouble("distance"))));}
                    catch(NumberFormatException error){extent.setError("Use a distance from 100 m to the reference length");}
                });
                addText(entries,"Suggested from the recorded GPS path. Confirm once; shorter out-and-backs turn earlier along the same outward leg.",12,muted,false,6);
            }
        }else addText(entries,"Choose one full reference run. Longer runs with GPS overlap are suggested, regardless of workout category.",14,muted,false,12);
        smallButton(entries,ref==null?"Choose reference":"Change reference",()->showTrainingReferencePicker(routeId,"route",()->renderTrainingRouteConfig(page,status,entries,routeId)));
        if(ref!=null)smallButton(entries,"Clear reference",()->trainingRouteRequest(page,status,entries,()->invoke("route_reference",routeId,"",LocalDate.now().toString(),settings().toString()),result->renderTrainingRouteConfig(page,status,entries,routeId)));
        if(ref!=null&&!ref.optBoolean("stale"))button(entries,"Use this route",true,()->trainingRouteRequest(page,status,entries,()->invoke("route_use",routeId,settings().toString()),result->{applyTrainingRoute(result.optJSONObject("selection"));page.dismiss();}));
        addText(entries,"Loop predictions repeat the course. One-way and longer out-and-back predictions label terrain beyond the measured reference as extrapolated. Starting point follows the reference, or its finish when reversed.",12,muted,false,12);
    }
    private void showTrainingReferencePicker(String routeId,String kind,Runnable changed){
        LinearLayout body=section();body.setPadding(dp(20),dp(8),dp(20),dp(20));
        TextView status=addText(body,"",13,muted,false,8);LinearLayout controls=section();body.addView(controls);
        EditText search=input(controls,"Search saved sessions",InputType.TYPE_CLASS_TEXT);
        LinearLayout filterSlot=section();controls.addView(filterSlot);final String[] category={"all"};
        LinearLayout list=section();final JSONArray[] rows={new JSONArray()};final int[] limit={30};final boolean[] loading={false},reviewing={false};
        Dialog page=fullScreen("Route reference",body,null);Runnable[] render={null};java.util.function.IntConsumer[] load=new java.util.function.IntConsumer[1];
        RouteReferencePreviews previews=new RouteReferencePreviews(page,list,()->loading[0]||reviewing[0]);
        Runnable[] renderFilters={null};renderFilters[0]=()->{
            filterSlot.removeAllViews();sessionFilters(filterSlot,category[0],key->{category[0]=key;limit[0]=30;renderFilters[0].run();render[0].run();});
        };renderFilters[0].run();
        addText(controls,"Newest first · Tap a session to compare longer GPS matches",12,muted,false,8);
        render[0]=()->{
            list.removeAllViews();previews.clearViews();String query=search.getText().toString().trim().toLowerCase(Locale.ROOT);int count=0;
            for(int i=0;i<rows[0].length();i++){
                JSONObject row=rows[0].optJSONObject(i);String searchable=row.optString("title")+" "+row.optString("date")+" "+ScatterPlot.label(row.optString("category"));
                if(!matchesSessionFilter(row,category[0])||!searchable.toLowerCase(Locale.ROOT).contains(query))continue;count++;if(count>limit[0])continue;
                LinearLayout card=new LinearLayout(this);card.setGravity(Gravity.CENTER_VERTICAL);card.setPadding(dp(10),dp(10),dp(10),dp(10));
                card.setBackground(MaterialUi.ripple(this,palette.container,16,palette.primary));card.setMinimumHeight(dp(80));card.setFocusable(true);
                previews.add(row,card);
                LinearLayout details=section();LinearLayout.LayoutParams detailsLp=new LinearLayout.LayoutParams(0,-2,1);detailsLp.leftMargin=dp(10);card.addView(details,detailsLp);
                String date=ScatterPlot.label(row.optString("category"))+" · "+sessionCardDate(row.optString("date"));
                addText(details,date,12,muted,true,0);
                TextView title=addText(details,row.optString("title"),14,ink,true,3);title.setMaxLines(2);title.setEllipsize(TextUtils.TruncateAt.END);
                String metrics=distanceText(row)+(row.isNull("duration")?"":" · "+raceTime(row.optDouble("duration")));
                addText(details,metrics,12,muted,false,3);
                if(needsReview(row))addText(details,"Needs review",11,palette.error,false,3);
                card.setContentDescription(date+", "+row.optString("title")+", "+metrics+". Compare longer GPS matches before choosing this reference.");
                card.setOnClickListener(v->{if(!loading[0]&&!reviewing[0]){
                    reviewing[0]=true;showTrainingReferenceMatches(routeId,row,page,changed,()->{reviewing[0]=false;previews.schedule();});
                }});
                LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(6);list.addView(card,lp);
            }
            if(count==0)addText(list,"No saved running sessions match. Try another filter or search, or sync more history.",14,muted,false,12);
            else addText(list,count+" matching sessions",12,muted,false,10);
            if(count>limit[0])smallButton(list,"Show more sessions",()->{limit[0]+=30;render[0].run();});
            if(loading[0])enable(list,false);
            previews.schedule();
        };
        addText(controls,"GPS previews load as you scroll and are saved for next time.",12,muted,false,8);
        controls.addView(list);
        smallButton(controls,"Reload saved sessions",()->load[0].accept(0));
        load[0]=scan->{if(loading[0])return;loading[0]=true;trainingRouteRequest(page,status,controls,()->{
            try{return invoke("route_candidates_v2",routeId,LocalDate.now().toString(),settings().toString(),scan);}
            finally{runOnUiThread(()->{loading[0]=false;previews.schedule();});}
        },result->{
            loading[0]=false;rows[0]=result.optJSONArray("candidates");render[0].run();
            status.setText("");
        });};
        search.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence text,int start,int count,int after){}public void onTextChanged(CharSequence text,int start,int before,int count){limit[0]=30;render[0].run();}public void afterTextChanged(Editable text){}});
        load[0].accept(0);
    }
    private void showTrainingReferenceMatches(String routeId,JSONObject original,Dialog picker,Runnable changed,Runnable closed){
        LinearLayout body=section();body.setPadding(dp(20),dp(8),dp(20),dp(20));
        TextView status=addText(body,"",13,muted,false,0);LinearLayout controls=section();body.addView(controls);
        Dialog page=fullScreen("Confirm route reference",body,null);final boolean[] loading={false};final int[] limit={10};
        final JSONObject[] data={null};Runnable[] render={null};java.util.function.IntConsumer[] load=new java.util.function.IntConsumer[1];
        RouteReferencePreviews previews=new RouteReferencePreviews(page,controls,()->loading[0]);
        page.setOnDismissListener(dialog->{controls.removeCallbacks(previews.load);closed.run();});
        Consumer<JSONObject> choose=row->{
            if(loading[0])return;loading[0]=true;
            trainingRouteRequest(page,status,controls,()->{
                try{return invoke("route_reference",routeId,row.optString("id"),LocalDate.now().toString(),settings().toString());}
                finally{runOnUiThread(()->{loading[0]=false;previews.schedule();});}
            },result->{page.dismiss();picker.dismiss();changed.run();});
        };
        render[0]=()->{
            controls.removeAllViews();previews.clearViews();JSONObject source=data[0].optJSONObject("original");
            addText(controls,"Your original selection",18,ink,true,4);
            referenceMatchCard(controls,source,previews,"Keep original selection",()->choose.accept(source));
            addText(controls,"Longer GPS matches",18,ink,true,20);
            addText(controls,"Longest first · These recordings cover the selected route. Keep your original or choose a longer reference below.",13,muted,false,6);
            JSONArray matches=data[0].optJSONArray("candidates");
            if(matches==null||matches.length()==0)addText(controls,"No longer matches found in checked recordings.",14,muted,false,12);
            else{
                addText(controls,matches.length()+" longer "+(matches.length()==1?"match":"matches"),12,muted,false,8);
                for(int i=0;i<Math.min(limit[0],matches.length());i++){
                    JSONObject candidate=matches.optJSONObject(i);referenceMatchCard(controls,candidate,previews,"Use this longer session",()->choose.accept(candidate));
                }
                if(matches.length()>limit[0])smallButton(controls,"Show more matches",()->{limit[0]+=10;render[0].run();});
            }
            int remaining=data[0].optInt("remaining");
            addText(controls,data[0].optInt("checked")+" longer recordings checked · "+remaining+" unchecked",12,muted,false,12);
            if(remaining>0)button(controls,"Check 5 more longer recordings",false,()->load[0].accept(5));
            if(!data[0].isNull("scan_error"))addText(controls,data[0].optString("scan_error"),13,palette.error,false,8);
            previews.schedule();
        };
        load[0]=scan->{
            if(loading[0])return;loading[0]=true;
            trainingRouteRequest(page,status,controls,()->{
                try{return invoke("route_matches",routeId,original.optString("id"),LocalDate.now().toString(),settings().toString(),scan);}
                finally{runOnUiThread(()->{loading[0]=false;previews.schedule();});}
            },result->{data[0]=result;render[0].run();});
        };
        button(controls,"Retry loading matches",false,()->load[0].accept(5));load[0].accept(5);
    }
    private void referenceMatchCard(LinearLayout parent,JSONObject row,RouteReferencePreviews previews,String action,Runnable choose){
        LinearLayout card=section();card.setPadding(dp(12),dp(12),dp(12),dp(12));card.setBackground(shape(palette.container,16));
        LinearLayout summary=new LinearLayout(this);summary.setGravity(Gravity.CENTER_VERTICAL);card.addView(summary);
        previews.add(row,summary);LinearLayout details=section();LinearLayout.LayoutParams info=new LinearLayout.LayoutParams(0,-2,1);info.leftMargin=dp(10);summary.addView(details,info);
        addText(details,ScatterPlot.label(row.optString("category"))+" · "+sessionCardDate(row.optString("date")),12,muted,true,0);
        addText(details,row.optString("title"),14,ink,true,4);
        addText(details,distanceText(row)+(row.isNull("duration")?"":" · "+raceTime(row.optDouble("duration"))),13,muted,false,4);
        button(card,action,action.equals("Keep original selection"),choose);
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(10);parent.addView(card,lp);
    }
    /** One missing GPS recording at a time, and only for a row currently in view. */
    private final class RouteReferencePreviews {
        final Dialog page;final LinearLayout list;final java.util.function.BooleanSupplier blocked;
        final java.util.LinkedHashMap<String,RouteThumbnail> views=new java.util.LinkedHashMap<>();
        final java.util.Map<String,JSONObject> outlines=new java.util.HashMap<>();
        final java.util.Set<String> failed=new java.util.HashSet<>();
        final Runnable load=this::loadVisible;boolean inFlight,paused;
        RouteReferencePreviews(Dialog page,LinearLayout list,java.util.function.BooleanSupplier blocked){
            this.page=page;this.list=list;this.blocked=blocked;
            list.getViewTreeObserver().addOnScrollChangedListener(this::schedule);
            list.addOnLayoutChangeListener((v,l,t,r,b,ol,ot,or,ob)->schedule());
            page.setOnDismissListener(dialog->list.removeCallbacks(load));
        }
        void clearViews(){views.clear();}
        void schedule(){list.removeCallbacks(load);if(page.isShowing())list.postDelayed(load,150);}
        void add(JSONObject row,LinearLayout parent){
            String id=row.optString("id");RouteThumbnail thumbnail=new RouteThumbnail(MainActivity.this,palette);views.put(id,thumbnail);
            parent.addView(thumbnail,new LinearLayout.LayoutParams(dp(68),dp(68)));
            if(row.has("outline")&&!row.isNull("outline"))outlines.put(id,row.optJSONObject("outline"));
            if(outlines.containsKey(id))thumbnail.showRoute(outlines.get(id));
            else if(failed.contains(id))thumbnail.showRetry(()->retry(id));
            else thumbnail.showWaiting();
        }
        void retry(String id){failed.remove(id);paused=false;RouteThumbnail view=views.get(id);if(view!=null)view.showWaiting();schedule();}
        void loadVisible(){
            if(isDestroyed()||!page.isShowing()||inFlight||blocked.getAsBoolean())return;
            if(syncRunning){schedule();return;}
            android.graphics.Rect visible=new android.graphics.Rect();
            for(java.util.Map.Entry<String,RouteThumbnail> entry:views.entrySet()){
                String id=entry.getKey();RouteThumbnail view=entry.getValue();
                if(outlines.containsKey(id)||failed.contains(id)||!view.getLocalVisibleRect(visible))continue;
                if(paused){view.showRetry(()->retry(id));continue;}
                inFlight=true;view.showLoading();
                BackendRuntime.WORKER.execute(()->{
                    JSONObject data=null;try{data=invoke("route",id);}catch(Exception ignored){}final JSONObject result=data;
                    runOnUiThread(()->{
                        inFlight=false;if(isDestroyed()||!page.isShowing())return;
                        RouteThumbnail current=views.get(id);
                        if(result!=null&&result.optBoolean("ok")){
                            JSONObject outline=result.optJSONObject("route");outlines.put(id,outline);if(current!=null)current.showRoute(outline);
                        }else{
                            // Pause automatic downloads after a connection error; a thumbnail offers retry.
                            failed.add(id);paused=true;if(current!=null)current.showRetry(()->retry(id));
                        }
                        schedule();
                    });
                });return;
            }
        }
    }
    private void showTrainingRoutePicker(){
        LinearLayout body=section();TextView status=addText(body,"",13,muted,false,0);LinearLayout controls=section();body.addView(controls);
        Dialog sheet=bottomSheet("Routes",body,null,null);
        trainingRouteRequest(sheet,status,controls,()->invoke("route_book",settings().toString()),result->{
            controls.removeAllViews();for(int i=0;i<savedTrainingRoutes.length();i++){
                JSONObject route=savedTrainingRoutes.optJSONObject(i),ref=route.optJSONObject("reference");String id=route.optString("id");boolean ready=ref!=null&&!ref.optBoolean("stale");
                button(controls,route.optString("name")+"\n"+routeShapeLabel(route.optString("shape"))+" · "+route.optString("surface")+(ready?"":" · Choose reference →"),false,()->{
                    if(!ready){sheet.dismiss();showTrainingRouteConfig(id);return;}
                    trainingRouteRequest(sheet,status,controls,()->invoke("route_use",id,settings().toString()),data->{applyTrainingRoute(data.optJSONObject("selection"));sheet.dismiss();});
                });
            }
            smallButton(controls,"Manage routes",()->{sheet.dismiss();showTrainingRouteManager();});
        });
    }
    private void applyTrainingRoute(JSONObject selection){
        if(selection==null)return;
        try{JSONObject state=settings();state.put("target_route_id",selection.getString("id")).put("target_route_name",selection.getString("name")).put("target_route_engine",2);
            for(String key:new String[]{"target_route_reference","target_interval_rates","target_legacy_elevation","target_workout_kind"})state.remove(key);
            preferences.edit().putString("settings",state.toString()).apply();profileDirty=true;conditionsNeedRecalc=true;
            if(elevationMigrationNote!=null)elevationMigrationNote.setVisibility(View.GONE);
            updateRouteConditionMode();if(screen==TARGETS&&conditionsFields!=null&&conditionsFields[0].isAttachedToWindow())saveInlineConditions();
        }catch(Exception error){message.setText("Couldn't apply the route. Try again.");}
    }
    private void clearTrainingRouteSelection(){
        if(elevationMigrationNote!=null)elevationMigrationNote.setVisibility(View.GONE);
        try{JSONObject state=settings();for(String key:new String[]{"target_route_id","target_route_name","target_route_reference","target_interval_rates","target_legacy_elevation","target_route_engine"})state.remove(key);preferences.edit().putString("settings",state.toString()).apply();updateRouteConditionMode();}catch(Exception ignored){}
    }
    private void refreshActiveTrainingRoute(){
        String id=setting("target_route_id","");if(id.isEmpty())return;String kind=setting("target_workout_kind","easy");
        BackendRuntime.WORKER.execute(()->{
            JSONObject result=null;try{result=invoke("route_use",id,settings().toString());}catch(Exception ignored){}final JSONObject data=result;
            runOnUiThread(()->{if(isDestroyed()||!id.equals(setting("target_route_id","")))return;
                if(data!=null&&data.optBoolean("ok"))applyTrainingRoute(data.optJSONObject("selection"));else{clearTrainingRouteSelection();profileDirty=true;message.setText("Route reference changed. Elevation is now manual; choose a route again when ready.");}
            });
        });
    }
    private void updateWorkoutConditionsSummary(JSONObject targets){
        if(workoutConditionsSummary==null)return;
        if(targets!=null&&targets.optInt("route_engine")==2){workoutConditionsSummary.setText(targets.has("route_error")?targets.optString("route_error"):targets.optString("route_name")+" · "+targets.optString("route_surface")+" · "+routeShapeLabel(targets.optString("route_shape"))+" · Tap a target for its route breakdown");return;}
        JSONObject workout=targets==null?null:targets.optJSONObject("workout");
        if(workout==null){workoutConditionsSummary.setText("Elevation is feet per mile; each prediction scales to its own distance.");return;}
        String value=workout.optString("route_name");if(!value.isEmpty())value+=" · ";value+=routeKindLabel(workout.optString("kind"));
        if(workout.has("distance"))value+=String.format(Locale.getDefault()," · %.1f %s · %s · +%.0f / −%.0f ft",workout.optDouble("distance")/(miles?1609.344:1000),miles?"mi":"km",raceTime(workout.optDouble("duration")),workout.optDouble("gain"),workout.optDouble("loss"))+" · "+workout.optString("basis");
        else if(workout.optString("kind").equals("intervals"))value+=" · Elevation is ft/mi";
        else value+=" · "+setting(workout.optString("kind").equals("easy_long")?"target_easy_long_minutes":"target_easy_minutes",workout.optString("kind").equals("easy_long")?"80":"45")+" min · Elevation is ft/mi";
        workoutConditionsSummary.setText(value);
    }
    private JSONObject routePlan(JSONObject targets,String kind){
        JSONArray plans=targets==null?null:targets.optJSONArray("route_plans");if(plans!=null)for(int i=0;i<plans.length();i++){JSONObject plan=plans.optJSONObject(i);if(plan!=null&&kind.equals(plan.optString("kind")))return plan;}return null;
    }
    private void showRoutePlan(String title,JSONObject plan){
        LinearLayout body=section();
        if(plan.has("error"))addText(body,plan.optString("error"),15,muted,false,12);
        else{
            addText(body,String.format(Locale.getDefault(),"%.2f %s · %s · +%.0f / −%.0f ft",plan.optDouble("distance")/(miles?1609.344:1000),miles?"mi":"km",raceTime(plan.optDouble("duration")),plan.optDouble("gain"),plan.optDouble("loss")),18,ink,true,12);
            if(!plan.isNull("turnaround"))addText(body,String.format(Locale.getDefault(),"Turn around %.2f %s from the start",plan.optDouble("turnaround")/(miles?1609.344:1000),miles?"mi":"km"),14,muted,false,8);
            if(plan.optDouble("work_distance")>0)addText(body,String.format(Locale.getDefault(),"Work only · %.2f %s · %s · +%.0f / −%.0f ft",plan.optDouble("work_distance")/(miles?1609.344:1000),miles?"mi":"km",raceTime(plan.optDouble("work_duration")),plan.optDouble("work_gain"),plan.optDouble("work_loss")),15,palette.primary,true,12);
            if(plan.optBoolean("extrapolated"))addText(body,"Beyond the recorded reference: terrain there is estimated from its average gain/loss.",13,muted,false,10);
            JSONArray phases=plan.optJSONArray("phases");if(phases!=null)for(int i=0;i<phases.length();i++){
                JSONObject phase=phases.optJSONObject(i);String kind=phase.optString("kind"),label=kind.equals("warmup")?"Warm-up · 128 bpm":kind.equals("cooldown")?"Cooldown · 128 bpm":kind.equals("walk")?"Walk after rep "+phase.optInt("rep"):kind.equals("work")?"Work rep "+phase.optInt("rep"):"Easy · 128 bpm";
                addText(body,label+" · "+raceTime(phase.optDouble("duration"))+String.format(Locale.getDefault()," · %.2f %s · +%.0f / −%.0f ft",(phase.optDouble("end")-phase.optDouble("start"))/(miles?1609.344:1000),miles?"mi":"km",phase.optDouble("gain"),phase.optDouble("loss")),13,muted,false,10);
            }
        }
        bottomSheet(title,body,null,null);
    }
    private void renderRouteEasyTargets(JSONObject targets,LinearLayout panel){
        addText(panel,"Easy pace · 128 bpm · "+targets.optString("route_surface"),16,ink,true,0);
        if(targets.has("route_error")){addText(panel,targets.optString("route_error"),13,muted,false,8);return;}
        for(String kind:new String[]{"easy","easy_long"}){
            JSONObject plan=routePlan(targets,kind);if(plan==null)continue;
            LinearLayout line=new LinearLayout(this);line.setGravity(Gravity.CENTER_VERTICAL);line.setPadding(0,dp(8),0,0);
            line.addView(text(routeKindLabel(kind)+" · "+setting(kind.equals("easy")?"target_easy_minutes":"target_easy_long_minutes",kind.equals("easy")?"45":"80")+" min",14,ink,false),new LinearLayout.LayoutParams(0,-2,1));
            line.addView(text(plan.has("error")?"—":easyPace(plan.optDouble("pace"))+(miles?" /mi":" /km"),20,ink,true));panel.addView(line);
            addText(panel,plan.has("error")?plan.optString("error"):String.format(Locale.getDefault(),"%.1f %s · +%.0f / −%.0f ft",plan.optDouble("distance")/(miles?1609.344:1000),miles?"mi":"km",plan.optDouble("gain"),plan.optDouble("loss"))+(plan.optBoolean("extrapolated")?" · extrapolated":""),11,muted,false,2);
            line.setOnClickListener(view->showRoutePlan(routeKindLabel(kind),plan));
        }
    }
    private String targetBasisPrefix(String source){return source.equals("predicted")?"target_prediction_":"target_trial_";}
    private boolean targetAdjusted(String source,String key){return "true".equals(setting(targetBasisPrefix(source)+key,source.equals("predicted")?"true":"false"));}
    private void applyTargetAdjustments(String source,boolean elevation,boolean weather){
        try{
            JSONObject state=settings();String prefix=targetBasisPrefix(source);
            state.put(prefix+"adjust_elevation",elevation);state.put(prefix+"adjust_temperature",weather);
            preferences.edit().putString("settings",state.toString()).apply();loadDashboard(false);
        }catch(Exception error){message.setText("Could not save target basis adjustments.");}
    }
    private void editTargetAdjustments(String source){
        LinearLayout form=section();
        addText(form,"Account for elevation and weather in past workouts when calculating this 5K basis. Conditions for your next workout are set separately below.",14,muted,false,8);
        Switch elevation=new Switch(this),weather=new Switch(this);elevation.setText("Elevation");weather.setText("Weather · temperature / dew point");
        elevation.setTextColor(ink);weather.setTextColor(ink);elevation.setMinHeight(dp(64));weather.setMinHeight(dp(64));
        elevation.setChecked(targetAdjusted(source,"adjust_elevation"));weather.setChecked(targetAdjusted(source,"adjust_temperature"));
        form.addView(elevation,new LinearLayout.LayoutParams(-1,-2));form.addView(weather,new LinearLayout.LayoutParams(-1,-2));
        bottomSheet("5K basis adjustments",form,"Apply adjustments",dialog->{dialog.dismiss();applyTargetAdjustments(source,elevation.isChecked(),weather.isChecked());});
    }
    private void targetBasisControls(LinearLayout basis,String source){
        boolean elevation=targetAdjusted(source,"adjust_elevation"),weather=targetAdjusted(source,"adjust_temperature"),both=elevation&&weather;
        MaterialUi.ButtonGroup controls=new MaterialUi.ButtonGroup(this,false);controls.setPadding(0,dp(6),0,0);
        controls.addView(adjustmentControl(elevation,weather,()->applyTargetAdjustments(source,!both,!both),()->editTargetAdjustments(source)));
        if(source.equals("predicted")){
            boolean normalized="intensity".equals(setting("target_prediction_mode","observed"));
            Button hr=chipButton("HR · "+(normalized?"On":"Off"),normalized,()->{saveSetting("target_prediction_mode",normalized?"observed":"intensity");loadDashboard(false);});
            hr.setPadding(dp(10),dp(8),dp(10),dp(8));hr.setEnabled(!busy);
            hr.setContentDescription("HR normalization. "+(normalized?"On. Turn off.":"Off. Turn on."));hr.setTooltipText("Heart-rate normalization for the 5K estimate");
            hr.setAccessibilityDelegate(new View.AccessibilityDelegate(){
                @Override public void onInitializeAccessibilityNodeInfo(View host,android.view.accessibility.AccessibilityNodeInfo info){
                    super.onInitializeAccessibilityNodeInfo(host,info);info.setClassName("android.widget.ToggleButton");info.setCheckable(true);info.setChecked(normalized);
                }
            });
            controls.addView(hr);
        }
        basis.addView(controls,new LinearLayout.LayoutParams(-1,-2));
    }
    private void renderTargets(){
        LinearLayout basis=card();String source=setting("target_source","predicted");
        basis.setPadding(dp(12),dp(12),dp(12),dp(12));
        String[] values={"predicted","latest","custom"};int selected=source.equals("custom")?2:source.equals("latest")?1:0;
        JSONObject targets=dashboardData.optJSONObject("targets");
        boolean valid=targets!=null&&!targets.has("error")&&source.equals(targets.optString("source"));
        LinearLayout basisHeader=new LinearLayout(this);basisHeader.setGravity(Gravity.CENTER_VERTICAL);
        basisHeader.addView(text("5K basis",14,ink,true),new LinearLayout.LayoutParams(0,-2,1));
        TextView basisTime=text(valid?raceTime(targets.optDouble("seconds")):"—",22,ink,true);basisHeader.addView(basisTime);basis.addView(basisHeader);
        MaterialUi.ButtonGroup sourceChoices=segmented(basis,new String[]{"Estimate","Latest trial","Custom"},selected,choice->{if(!values[choice].equals(source)){saveSetting("target_source",values[choice]);loadDashboard(false);}});
        LinearLayout.LayoutParams choicesLp=(LinearLayout.LayoutParams)sourceChoices.getLayoutParams();choicesLp.topMargin=dp(6);sourceChoices.setLayoutParams(choicesLp);
        if(source.equals("custom")){
            EditText custom=input(basis,"Custom 5K time · mm:ss",InputType.TYPE_CLASS_TEXT);custom.setHint("20:00");custom.setText(setting("target_time",""));
            button(basis,"Update targets",true,()->{String value=custom.getText().toString().trim();if(!validTargetTime(value)){custom.setError("Use mm:ss between 5:00 and 120:00");return;}saveSetting("target_time",value);custom.clearFocus();((android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(custom.getWindowToken(),0);loadDashboard(false);});
        }
        if(!valid)addText(basis,targets==null?"Sync your training data to calculate targets.":targets.optString("error","Updating your 5K basis…"),14,palette.error,false,6);
        if(!source.equals("custom")){
            boolean elevation=valid?targets.optBoolean("basis_adjust_elevation"):targetAdjusted(source,"adjust_elevation");
            boolean weather=valid?targets.optBoolean("basis_adjust_temperature"):targetAdjusted(source,"adjust_temperature");
            boolean hr="intensity".equals(valid?targets.optString("basis_prediction_mode"):setting("target_prediction_mode","observed"));
            String description=elevation?(weather?"Elevation + weather adjusted":"Elevation adjusted"):(weather?"Weather adjusted":"Unadjusted");
            if(source.equals("predicted"))description+=" · "+(hr?"HR normalized":"HR off");
            if(valid&&targets.has("basis_date"))description+=" · "+sessionCardDate(targets.optString("basis_date"));
            addText(basis,description,12,muted,false,6);
            targetBasisControls(basis,source);
        }
        LinearLayout.LayoutParams basisLp=(LinearLayout.LayoutParams)basis.getLayoutParams();basisLp.bottomMargin=dp(10);basis.setLayoutParams(basisLp);
        renderTargetConditions();
        targetPaces=section();content.addView(targetPaces,new LinearLayout.LayoutParams(-1,-2));
        targetPaceResults=section();targetPaces.addView(targetPaceResults,new LinearLayout.LayoutParams(-1,-2));
        equivalentRaceCard=card(targetPaces);equivalentRaceCard.setPadding(dp(12),dp(12),dp(12),dp(8));
        addText(equivalentRaceCard,"Equivalent race times",20,ink,false,0);
        raceRows=section();equivalentRaceCard.addView(raceRows,new LinearLayout.LayoutParams(-1,-2));
        renderRaceDistanceField(equivalentRaceCard);
        renderTargetPaces(targets,valid);
        if(conditionsNeedRecalc)conditionsHandler.post(()->{if(screen==TARGETS&&!isDestroyed())saveInlineConditions();});
        conditionsHandler.post(weatherAuto);
    }
    private void renderTargetPaces(JSONObject targets,boolean valid){
        targetPaceResults.removeAllViews();raceRows.removeAllViews();targetPaces.setAlpha(1);
        updateWorkoutConditionsSummary(targets);
        equivalentRaceCard.setVisibility(valid?View.VISIBLE:View.GONE);
        if(!valid){renderEasyTargets(targets);return;}
        JSONArray rows=targets.optJSONArray("rows");
        MaterialUi.ButtonGroup targetTiles=new MaterialUi.ButtonGroup(this,true);
        LinearLayout.LayoutParams tilesLp=new LinearLayout.LayoutParams(-1,-2);tilesLp.bottomMargin=dp(12);targetPaceResults.addView(targetTiles,tilesLp);
        if(rows!=null)for(int i=0;i<rows.length();i++){
            JSONObject row=rows.optJSONObject(i);String category=row.optString("category");LinearLayout pace=section();
            pace.setPadding(dp(10),dp(10),dp(10),dp(10));
            boolean featured=i==0;pace.setBackground(shape(featured?palette.primaryContainer:palette.container,16));
            int foreground=featured?palette.onPrimaryContainer:ink;
            String name=category.substring(0,1).toUpperCase(Locale.getDefault())+category.substring(1),shown=paceValue(row.optDouble("pace",Double.NaN));
            addText(pace,name,13,foreground,true,0);
            addText(pace,row.optString("reps").replace("-min reps"," min"),12,foreground,false,2);
            TextView value=addText(pace,shown,26,foreground,true,6);value.setMaxLines(1);value.setAutoSizeTextTypeUniformWithConfiguration(18,26,1,android.util.TypedValue.COMPLEX_UNIT_SP);
            addText(pace,miles?"min/mi":"min/km",11,foreground,false,0);
            JSONObject plan=routePlan(targets,category);
            if(plan!=null){if(!plan.has("error"))addText(pace,String.format(Locale.getDefault(),"+%.0f / −%.0f ft",plan.optDouble("work_gain"),plan.optDouble("work_loss"))+(plan.optBoolean("extrapolated")?" *":""),10,foreground,false,4);pace.setOnClickListener(view->showRoutePlan(name,plan));pace.setTooltipText("Route workout breakdown");}
            pace.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);pace.setContentDescription(name+" intervals. "+row.optString("reps")+". Target pace "+shown+(miles?" minutes per mile":" minutes per kilometre"));
            for(int child=0;child<pace.getChildCount();child++)pace.getChildAt(child).setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
            targetTiles.addView(pace);
        }
        renderEasyTargets(targets);
        LinearLayout races=raceRows;JSONArray entries=targets.optJSONArray("races");
        LinearLayout labels=new LinearLayout(this);labels.setPadding(0,dp(10),0,dp(2));
        raceColumn(labels,"Distance",11,muted,false,Gravity.START,1.2f);
        raceColumn(labels,"Pace"+(miles?" /mi":" /km"),11,muted,false,Gravity.END,1);
        raceColumn(labels,"Time",11,muted,false,Gravity.END,1);races.addView(labels);
        customRacePace.setText("—");customRaceTime.setText("—");customRacePace.setOnClickListener(null);customRaceTime.setOnClickListener(null);
        boolean extrapolated=false;
        if(entries!=null)for(int i=0;i<entries.length();i++){
            JSONObject row=entries.optJSONObject(i);
            extrapolated|=row.optBoolean("extrapolated");
            // The model publishes five standard distances followed by the optional custom distance.
            if(i>=5){customRacePace.setText(paceValue(row.optDouble("pace",Double.NaN)));customRaceTime.setText(sessionTimeValue(row.optDouble("duration",Double.NaN)));if(row.has("gain")){customRacePace.setOnClickListener(view->showRoutePlan("Custom race",row));customRaceTime.setOnClickListener(view->showRoutePlan("Custom race",row));}continue;}
            LinearLayout line=new LinearLayout(this);line.setGravity(Gravity.CENTER_VERTICAL);line.setPadding(0,dp(6),0,dp(6));
            raceColumn(line,row.optString("label")+(row.optBoolean("extrapolated")?" *":""),14,ink,false,Gravity.START,1.2f);
            raceColumn(line,paceValue(row.optDouble("pace",Double.NaN)),15,muted,false,Gravity.END,1);
            raceColumn(line,sessionTimeValue(row.optDouble("duration",Double.NaN)),15,ink,true,Gravity.END,1);races.addView(line);
            if(row.has("gain"))line.setOnClickListener(view->showRoutePlan(row.optString("label"),row));
        }
        if(extrapolated)addText(races,"* Beyond recorded coverage · average terrain estimate. Tap for details.",11,muted,false,6);
    }
    private TextView raceColumn(LinearLayout parent,String value,int size,int color,boolean bold,int gravity,float weight){
        TextView cell=text(value,size,color,bold);cell.setGravity(gravity);cell.setPadding(dp(2),0,dp(2),0);
        parent.addView(cell,new LinearLayout.LayoutParams(0,-2,weight));
        return cell;
    }
    private void renderEasyTargets(JSONObject targets){
        LinearLayout easy=card(targetPaceResults);easy.setPadding(dp(12),dp(10),dp(12),dp(10));
        if(targets!=null&&targets.optInt("route_engine")==2){renderRouteEasyTargets(targets,easy);return;}
        addText(easy,"Easy pace · 128 bpm",16,ink,true,0);
        JSONArray estimates=targets==null?null:targets.optJSONArray("easy");
        for(int i=0;i<2;i++){
            String surface=i==0?"road":"trail",label=i==0?"Road":"Trail";JSONObject estimate=null;
            if(estimates!=null)for(int j=0;j<estimates.length();j++){JSONObject entry=estimates.optJSONObject(j);if(entry!=null&&surface.equals(entry.optString("surface")))estimate=entry;}
            LinearLayout line=new LinearLayout(this);line.setGravity(Gravity.CENTER_VERTICAL);line.setPadding(0,dp(6),0,0);
            line.addView(text(label,14,ink,false),new LinearLayout.LayoutParams(0,-2,1));
            boolean available=estimate!=null&&!estimate.has("error")&&Double.isFinite(estimate.optDouble("pace",Double.NaN));
            String pace=available?easyPace(estimate.optDouble("pace"))+(miles?" /mi":" /km"):"—";
            line.addView(text(pace,20,ink,true));easy.addView(line);
            if(available){
                String context=estimate.optInt("samples")+" runs · "+String.format(Locale.getDefault(),"elevation over %.1f %s",estimate.optDouble("distance_basis")/(miles?1609.344:1000),miles?"mi":"km");
                String range=easyPace(estimate.optDouble("pace_low"))+"–"+easyPace(estimate.optDouble("pace_high"))+(miles?" /mi":" /km");
                addText(easy,"Typical "+range+" · "+context,11,muted,false,0);
            }else addText(easy,estimate==null?"Sync recent easy runs with pace and HR.":estimate.optString("error"),12,muted,false,0);
        }
        addText(easy,"Estimates for entered conditions; trail pace also varies with terrain.",11,muted,false,6);
    }
    private String easyPace(double pace){
        double displayed=pace*(miles?1.609344:1);
        return ScatterPlot.pace(Math.round(displayed/5)*5,false);
    }
    private String raceTime(double value){long seconds=Math.round(value);return seconds>=3600?String.format(Locale.getDefault(),"%d:%02d:%02d",seconds/3600,seconds/60%60,seconds%60):ScatterPlot.pace(value,false);}
    private boolean validTargetTime(String value){
        try{String[] parts=value.split(":",-1);if(parts.length<2||parts.length>3)return false;long seconds=0;for(int i=0;i<parts.length;i++){if(!parts[i].matches("[0-9]+"))return false;int part=Integer.parseInt(parts[i]);if(i>0&&part>=60)return false;seconds=seconds*60+part;}return seconds>=300&&seconds<=7200;}catch(Exception e){return false;}
    }
    private void renderTargetConditions(){
        LinearLayout conditions=section();LinearLayout header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);
        header.addView(text("Conditions",14,ink,true),new LinearLayout.LayoutParams(0,-2,1));
        localWeatherButton=chipButton("Local weather",false,()->requestLocalWeather(true));localWeatherButton.setTextSize(12);localWeatherButton.setPadding(dp(8),dp(6),dp(8),dp(6));
        localWeatherButton.setContentDescription("Use current local temperature and humidity. Refresh now, including during a manual override.");
        localWeatherButton.setTooltipText("Fill temperature and humidity using approximate location and Open-Meteo");
        MaterialUi.ButtonGroup actions=new MaterialUi.ButtonGroup(this,false);actions.addView(localWeatherButton);
        Button routes=chipButton("Routes",false,this::showTrainingRoutePicker);routes.setTextSize(12);routes.setPadding(dp(8),dp(6),dp(8),dp(6));actions.addView(routes);
        manualElevationButton=chipButton("Manual",false,()->{clearTrainingRouteSelection();saveInlineConditions();});manualElevationButton.setTextSize(12);manualElevationButton.setPadding(dp(8),dp(6),dp(8),dp(6));manualElevationButton.setContentDescription("Switch from route profiles to manual elevation rates");actions.addView(manualElevationButton);
        Button reset=chipButton("Reset",false,this::resetTargetConditions);reset.setTextSize(12);reset.setPadding(dp(8),dp(6),dp(8),dp(6));
        reset.setContentDescription("Reset conditions to 45 degrees Fahrenheit, no humidity, and zero elevation gain and loss. Keep defaults for one hour.");actions.addView(reset);
        header.addView(actions,new LinearLayout.LayoutParams(0,-2,2));conditions.addView(header);
        MaterialUi.MetricGroup fields=new MaterialUi.MetricGroup(this);fields.setPadding(0,dp(6),0,0);
        conditionsFields=new EditText[4];String[] labels={"Temp °F","Humidity %","+ft/mi","−ft/mi"};
        String[] descriptions={"Temperature in Fahrenheit","Humidity percent, optional","Elevation gain in feet per mile","Elevation loss in feet per mile"};
        for(int i=0;i<4;i++){
            final int index=i;LinearLayout column=section();TextView label=addText(column,labels[i],12,muted,false,0);
            if(i>=2)elevationConditionColumns[i-2]=column;
            EditText field=new EditText(this){
                @Override public boolean onKeyPreIme(int key,android.view.KeyEvent event){
                    if(key==android.view.KeyEvent.KEYCODE_BACK&&event.getAction()==android.view.KeyEvent.ACTION_UP&&hasFocus()){finishConditionEditing();return true;}
                    return super.onKeyPreIme(key,event);
                }
            };field.setId(View.generateViewId());label.setLabelFor(field.getId());field.setSaveEnabled(false);
            field.setSingleLine(true);field.setInputType(InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_DECIMAL|(i==0?InputType.TYPE_NUMBER_FLAG_SIGNED:0));
            field.setTextSize(16);field.setTextColor(ink);field.setHintTextColor(muted);field.setMinimumHeight(dp(48));field.setMinWidth(dp(64));field.setPadding(dp(8),dp(6),dp(8),dp(6));field.setBackground(inputBackground());
            field.setText(setting(TargetConditions.KEYS[i],TargetConditions.DEFAULTS[i]));field.setHint(i==1?"—":"0");field.setContentDescription(descriptions[i]);field.setImeOptions(android.view.inputmethod.EditorInfo.IME_ACTION_DONE);
            LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(3);column.addView(field,lp);fields.addView(column);conditionsFields[i]=field;
            field.addTextChangedListener(new TextWatcher(){
                public void beforeTextChanged(CharSequence text,int start,int count,int after){}
                public void onTextChanged(CharSequence text,int start,int before,int count){
                    if(bindingConditions)return;
                    if(index>=2)clearTrainingRouteSelection();
                    if(index<2){
                        preferences.edit().putLong("weather_manual_until",System.currentTimeMillis()+WeatherPolicy.HOUR).remove("weather_observed_at").apply();
                        weatherError=null;if(localWeather!=null)localWeather.cancel();updateWeatherControls();
                        conditionsHandler.removeCallbacks(weatherAuto);conditionsHandler.postDelayed(weatherAuto,WeatherPolicy.HOUR);
                    }
                    saveInlineConditions();
                }
                public void afterTextChanged(Editable text){}
            });
            field.setOnFocusChangeListener((view,focused)->{if(!focused&&!TargetConditions.valid(index,field.getText().toString()))field.setError(index==1?"Use 0–100":"Enter a valid number");});
            field.setOnEditorActionListener((view,action,event)->{
                if(action==android.view.inputmethod.EditorInfo.IME_ACTION_DONE||(event!=null&&event.getKeyCode()==android.view.KeyEvent.KEYCODE_ENTER&&event.getAction()==android.view.KeyEvent.ACTION_UP)){finishConditionEditing();return true;}
                return false;
            });
        }
        conditions.addView(fields,new LinearLayout.LayoutParams(-1,-2));
        workoutConditionsSummary=addText(conditions,"",11,muted,false,4);
        String migration=setting("target_legacy_elevation","");elevationMigrationNote=addText(conditions,migration,12,muted,false,4);elevationMigrationNote.setVisibility(migration.isEmpty()?View.GONE:View.VISIBLE);
        conditionsStatus=addText(conditions,conditionsStatusText(),11,muted,false,4);
        conditionsStatus.setMovementMethod(android.text.method.LinkMovementMethod.getInstance());updateConditionsStatus();updateWeatherControls();
        updateRouteConditionMode();
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.bottomMargin=dp(10);content.addView(conditions,lp);
    }
    private void updateRouteConditionMode(){
        boolean route="2".equals(setting("target_route_engine",""))&&!setting("target_route_id","").isEmpty();
        for(View column:elevationConditionColumns)if(column!=null)column.setVisibility(route?View.GONE:View.VISIBLE);
        if(manualElevationButton!=null)manualElevationButton.setVisibility(route?View.VISIBLE:View.GONE);
    }
    private void resetTargetConditions(){
        if(conditionsFields==null)return;
        if(localWeather!=null)localWeather.cancel();weatherError=null;
        clearTrainingRouteSelection();
        preferences.edit().putLong("weather_manual_until",System.currentTimeMillis()+WeatherPolicy.HOUR).remove("weather_observed_at").apply();
        bindingConditions=true;
        try{for(int i=0;i<conditionsFields.length;i++){conditionsFields[i].setText(TargetConditions.DEFAULTS[i]);conditionsFields[i].setError(null);}}
        finally{bindingConditions=false;}
        root.requestFocus();((android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(root.getWindowToken(),0);
        saveInlineConditions();updateWeatherControls();
        conditionsHandler.removeCallbacks(weatherAuto);conditionsHandler.postDelayed(weatherAuto,WeatherPolicy.HOUR);
    }
    private String conditionsStatusText(){
        if(weatherError!=null)return weatherError;
        if(weatherPermissionPending)return "Allow approximate location for local weather";
        if(localWeather!=null&&localWeather.running())return "Loading local weather…";
        long until=preferences.getLong("weather_manual_until",0);
        if(WeatherPolicy.held(System.currentTimeMillis(),until))return "Saved · manual weather until "+weatherTime(until);
        long observed=preferences.getLong("weather_observed_at",0);
        return observed>0?"Weather · "+weatherTime(observed)+" · Open-Meteo":"Edits save automatically · local weather uses Open-Meteo";
    }
    private String weatherTime(long time){return java.time.Instant.ofEpochMilli(time).atZone(java.time.ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("h:mm a",Locale.getDefault()));}
    private void updateConditionsStatus(){
        if(conditionsStatus==null||screen!=TARGETS)return;String value=conditionsStatusText();
        android.text.SpannableString label=new android.text.SpannableString(value);int source=value.indexOf("Open-Meteo");
        if(source>=0)label.setSpan(new android.text.style.URLSpan("https://open-meteo.com/"),source,source+10,android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        conditionsStatus.setText(label);
    }
    private boolean weatherPermission(){return checkSelfPermission("android.permission.ACCESS_COARSE_LOCATION")==android.content.pm.PackageManager.PERMISSION_GRANTED;}
    private void updateWeatherControls(){if(localWeatherButton!=null&&screen==TARGETS)localWeatherButton.setEnabled(!busy&&!weatherPermissionPending&&(localWeather==null||!localWeather.running()));}
    private void maybeAutofillWeather(){
        conditionsHandler.removeCallbacks(weatherAuto);
        if(!foreground||isDestroyed()||!authenticated||!backendReady||weatherPermissionPending||localWeather==null||localWeather.running())return;
        long now=System.currentTimeMillis(),until=preferences.getLong("weather_manual_until",0);
        if(WeatherPolicy.held(now,until)){conditionsHandler.postDelayed(weatherAuto,until-now);return;}
        if(!WeatherPolicy.shouldRefresh(now,until,preferences.getLong("weather_last_fetch",0),preferences.getLong("weather_last_attempt",0)))return;
        if(!weatherPermission()&&(busy||screen!=TARGETS||preferences.getBoolean("weather_permission_asked",false)))return;
        requestLocalWeather(false);
    }
    private void requestLocalWeather(boolean manual){
        if(!foreground||isDestroyed()||(manual&&busy)||weatherPermissionPending||localWeather==null||localWeather.running())return;
        if(!weatherPermission()){
            weatherPermissionPending=true;weatherPermissionManual=manual;weatherError=null;
            preferences.edit().putBoolean("weather_permission_asked",true).apply();updateWeatherControls();updateConditionsStatus();
            requestPermissions(new String[]{"android.permission.ACCESS_COARSE_LOCATION"},42);return;
        }
        long now=System.currentTimeMillis();
        if(!WeatherPolicy.shouldRequest(manual,now,preferences.getLong("weather_manual_until",0),preferences.getLong("weather_last_fetch",0),preferences.getLong("weather_last_attempt",0)))return;
        // Persist before starting so failures, lifecycle changes and reopening cannot bypass the limit.
        preferences.edit().putLong("weather_last_attempt",now).apply();weatherError=null;
        localWeather.request((data,error)->{
            if(isDestroyed()||!foreground)return;
            weatherError=error;
            if(data!=null){
                try{
                    JSONObject state=settings();state.put("target_temperature",data.temperatureText());state.put("target_humidity",data.humidityText());
                    preferences.edit().putString("settings",state.toString()).putLong("weather_manual_until",0)
                        .putLong("weather_last_fetch",System.currentTimeMillis()).putLong("weather_observed_at",data.time).apply();profileDirty=true;conditionsNeedRecalc=true;
                    if(screen==TARGETS&&conditionsFields!=null&&conditionsFields[0].isAttachedToWindow()){
                        bindingConditions=true;try{conditionsFields[0].setText(data.temperatureText());conditionsFields[1].setText(data.humidityText());}finally{bindingConditions=false;}
                        saveInlineConditions();
                    }
                }catch(Exception problem){weatherError="Couldn't save local weather. Edit the fields or try again.";}
            }
            updateWeatherControls();updateConditionsStatus();
        });
        updateWeatherControls();updateConditionsStatus();
    }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] grants){
        super.onRequestPermissionsResult(request,permissions,grants);if(request!=42)return;
        weatherPermissionPending=false;
        if(weatherPermission()){
            if(foreground)requestLocalWeather(weatherPermissionManual);else weatherAfterPermission=true;
        }else weatherError="Location access wasn't allowed. You can edit conditions manually or enable it in app settings.";
        updateWeatherControls();updateConditionsStatus();
    }
    private void saveInlineConditions(){
        if(conditionsFields==null||conditionsStatus==null)return;
        if(conditionsRefresh!=null)conditionsHandler.removeCallbacks(conditionsRefresh);conditionsRevision++;
        String[] values=new String[4];
        for(int i=0;i<4;i++){
            values[i]=conditionsFields[i].getText().toString().trim();
            if(!TargetConditions.valid(i,values[i])){conditionsStatus.setText("Finish editing to update paces");if(targetPaces!=null)targetPaces.setAlpha(.55f);return;}
            conditionsFields[i].setError(null);
        }
        try{
            JSONObject state=settings();for(int i=0;i<4;i++)state.put(TargetConditions.KEYS[i],values[i]);
            preferences.edit().putString("settings",state.toString()).apply();profileDirty=true;conditionsNeedRecalc=true;conditionsStatus.setText("Saved · updating paces…");
            scheduleTargetRefresh();
        }catch(Exception error){conditionsStatus.setText("Couldn't save conditions. Try again.");}
    }
    private void scheduleTargetRefresh(){
        if(conditionsRefresh!=null)conditionsHandler.removeCallbacks(conditionsRefresh);conditionsRevision++;
        profileDirty=true;conditionsNeedRecalc=true;
        if(targetPaces!=null)targetPaces.setAlpha(.55f);
        final long revision=conditionsRevision;final LinearLayout output=targetPaces;
        conditionsRefresh=()->refreshConditionPaces(revision,output);conditionsHandler.postDelayed(conditionsRefresh,500);
    }
    private void refreshConditionPaces(long revision,LinearLayout output){
        if(isDestroyed()||!foreground||screen!=TARGETS||output!=targetPaces||revision!=conditionsRevision)return;
        if(busy||conditionsInFlight){conditionsHandler.postDelayed(conditionsRefresh,300);return;}
        try{
            final String config=settings().toString();conditionsInFlight=true;
            BackendRuntime.WORKER.execute(()->{
                JSONObject result=null;try{result=invoke("cached_dashboard",LocalDate.now().toString(),days,config);}catch(Exception ignored){}
                final JSONObject updated=result;
                runOnUiThread(()->{
                    conditionsInFlight=false;
                    if(isDestroyed()||screen!=TARGETS||output!=targetPaces||revision!=conditionsRevision)return;
                    if(updated!=null&&updated.optBoolean("ok")){
                        dashboardData=updated;profileDirty=false;conditionsNeedRecalc=false;JSONObject targets=updated.optJSONObject("targets");renderTargetPaces(targets,targets!=null&&!targets.has("error"));updateConditionsStatus();
                    }else{output.setAlpha(1);conditionsStatus.setText("Conditions saved. Reopen Targets to refresh paces.");}
                });
            });
        }catch(Exception error){conditionsInFlight=false;conditionsStatus.setText("Conditions saved. Reopen Targets to refresh paces.");}
    }
    private void renderRaceDistanceField(LinearLayout parent){
        LinearLayout line=new LinearLayout(this);line.setGravity(Gravity.CENTER_VERTICAL);line.setPadding(0,dp(6),0,dp(6));
        LinearLayout distanceCell=new LinearLayout(this);distanceCell.setGravity(Gravity.CENTER_VERTICAL);distanceCell.setPadding(dp(2),0,dp(2),0);
        line.addView(distanceCell,new LinearLayout.LayoutParams(0,-2,1.2f));
        EditText distance=new EditText(this){
            @Override public boolean onKeyPreIme(int key,android.view.KeyEvent event){
                if(key==android.view.KeyEvent.KEYCODE_BACK&&event.getAction()==android.view.KeyEvent.ACTION_UP&&hasFocus()){finishConditionEditing();return true;}
                return super.onKeyPreIme(key,event);
            }
        };
        raceDistanceField=distance;distance.setId(View.generateViewId());distance.setSaveEnabled(false);
        distance.setSingleLine(true);distance.setInputType(InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_DECIMAL);
        distance.setTextSize(14);distance.setTextColor(ink);distance.setHintTextColor(muted);distance.setMinimumHeight(dp(48));distance.setMinWidth(0);
        distance.setPadding(dp(6),dp(6),dp(6),dp(6));distance.setBackground(inputBackground());distance.setHint("Distance");
        distance.setContentDescription("Custom race distance in "+(miles?"miles":"kilometres")+". Saves automatically. Clear to remove.");
        distance.setImeOptions(android.view.inputmethod.EditorInfo.IME_ACTION_DONE);
        String saved=setting("race_distance_miles","");if(!miles&&!saved.isEmpty())try{saved=String.format(Locale.ROOT,"%.3f",Double.parseDouble(saved)*1.609344);}catch(Exception ignored){}distance.setText(saved);
        distanceCell.addView(distance,new LinearLayout.LayoutParams(0,-2,1));
        TextView unit=text(miles?"mi":"km",12,muted,false);unit.setPadding(dp(3),0,0,0);distanceCell.addView(unit);
        customRacePace=raceColumn(line,"—",15,muted,false,Gravity.END,1);
        customRaceTime=raceColumn(line,"—",15,ink,true,Gravity.END,1);parent.addView(line,new LinearLayout.LayoutParams(-1,-2));
        distance.addTextChangedListener(new TextWatcher(){
            public void beforeTextChanged(CharSequence text,int start,int count,int after){}
            public void onTextChanged(CharSequence text,int start,int before,int count){saveInlineRaceDistance();}
            public void afterTextChanged(Editable text){}
        });
        distance.setOnEditorActionListener((view,action,event)->{
            if(action==android.view.inputmethod.EditorInfo.IME_ACTION_DONE||(event!=null&&event.getKeyCode()==android.view.KeyEvent.KEYCODE_ENTER&&event.getAction()==android.view.KeyEvent.ACTION_UP)){finishConditionEditing();return true;}
            return false;
        });
    }
    private void saveInlineRaceDistance(){
        if(raceDistanceField==null)return;
        String value=raceDistanceField.getText().toString().trim();
        try{
            if(!value.isEmpty()){
                double n=Double.parseDouble(value)/(miles?1:1.609344);
                if(!Double.isFinite(n)||n<=0||n>200)throw new NumberFormatException();
                value=Double.toString(n);
            }
        }catch(NumberFormatException error){raceDistanceField.setError("Use a distance above 0 and up to "+(miles?"200 miles":"321.9 km"));return;}
        raceDistanceField.setError(null);
        if(value.equals(setting("race_distance_miles","")))return;
        try{
            JSONObject state=settings();state.put("race_distance_miles",value);
            preferences.edit().putString("settings",state.toString()).apply();scheduleTargetRefresh();
        }catch(Exception error){raceDistanceField.setError("Couldn't save distance. Try again.");}
    }
    private boolean needsReview(JSONObject run) {
        if(run==null)return false;
        if(run.has("needs_review"))return run.optBoolean("needs_review");
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
    private boolean matchesSessionFilter(JSONObject row,String filter){
        return "attention".equals(filter)?needsReview(row):"all".equals(filter)||filter.equals(row.optString("category"));
    }
    private void sessionFilters(LinearLayout parent,String selected,Consumer<String> choose){
        HorizontalScrollView filters=new HorizontalScrollView(this);filters.setHorizontalScrollBarEnabled(false);
        LinearLayout chips=new LinearLayout(this);int active=0;
        for(int i=0;i<SESSION_FILTER_KEYS.length;i++){
            String key=SESSION_FILTER_KEYS[i];if(key.equals(selected))active=i;
            Button chip=chipButton(SESSION_FILTER_LABELS[i],key.equals(selected),()->choose.accept(key));chip.setTextSize(12);
            chip.setAccessibilityDelegate(new View.AccessibilityDelegate(){@Override public void onInitializeAccessibilityNodeInfo(View host,android.view.accessibility.AccessibilityNodeInfo info){super.onInitializeAccessibilityNodeInfo(host,info);info.setClassName("android.widget.RadioButton");info.setCheckable(true);info.setChecked(key.equals(selected));}});
            LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-2,-2);lp.rightMargin=dp(6);chips.addView(chip,lp);
        }
        filters.addView(chips);LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(6);parent.addView(filters,lp);
        final int index=active;filters.post(()->filters.scrollTo(chips.getChildAt(index).getLeft(),0));
    }
    private void renderSessions() {
        EditText search=new EditText(this);search.setSingleLine(true);search.setTextSize(15);search.setTextColor(ink);
        search.setHint("Search session titles");search.setHintTextColor(muted);search.setPadding(dp(14),0,dp(14),0);search.setBackground(shape(palette.high,28));
        search.setMinimumHeight(dp(48));search.setInputType(InputType.TYPE_CLASS_TEXT);search.setText(query);LinearLayout.LayoutParams searchLp=new LinearLayout.LayoutParams(-1,-2);content.addView(search,searchLp);
        sessionFilters(content,runFilter,key->{runFilter=key;visibleRuns=30;renderRuns(null);});
        runList=new LinearLayout(this);runList.setOrientation(LinearLayout.VERTICAL);content.addView(runList);renderRunList();
        search.addTextChangedListener(new TextWatcher(){
            public void beforeTextChanged(CharSequence v,int start,int count,int after){}
            public void onTextChanged(CharSequence v,int start,int before,int count){query=v.toString();visibleRuns=30;renderRunList();}
            public void afterTextChanged(Editable value){}
        });
    }
    private void renderRunList(){
        runList.removeAllViews();JSONArray runs=dashboardData.optJSONArray("runs");int matching=0;
        if(runs!=null)for(int i=0;i<runs.length();i++){
            JSONObject run=runs.optJSONObject(i);if(run==null)continue;
            if(!run.optString("title").toLowerCase(Locale.ROOT).contains(query.toLowerCase(Locale.ROOT)))continue;
            if(!matchesSessionFilter(run,runFilter))continue;
            matching++;if(matching>visibleRuns)continue;
            sessionCard(runList,run);
        }
        if(matching==0)addText(runList,"No sessions match. Try another filter or date range.",15,muted,false,24);
        else{addText(runList,matching+" matching sessions",12,muted,false,16);if(matching>visibleRuns){Button more=actionButton("Show more sessions",false,()->{visibleRuns+=30;renderRunList();});LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(12);runList.addView(more,lp);}}
    }
    private String sessionCardDate(String day){
        try{
            LocalDate date=LocalDate.parse(day);
            return date.format(DateTimeFormatter.ofPattern(date.getYear()==LocalDate.now().getYear()?"MMM d":"MMM d, yyyy",Locale.getDefault()));
        }catch(Exception error){return day;}
    }
    private String friendlyDate(String day){
        try{LocalDate date=LocalDate.parse(day);if(date.equals(LocalDate.now()))return "Today";if(date.equals(LocalDate.now().minusDays(1)))return "Yesterday";return date.format(DateTimeFormatter.ofPattern("EEE, MMM d, yyyy",Locale.getDefault()));}catch(Exception error){return day;}
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
        if(!run.isNull("work_pace"))detail+="\nRecorded work pace: "+ScatterPlot.pace(run.optDouble("work_pace"),miles)+(miles?" /mi":" /km");
        if(run.has("work_source"))detail+="\nWork metrics: "+run.optString("work_source");
        if(!run.isNull("elevation_gain"))detail+="\nElevation gain: "+Math.round(run.optDouble("elevation_gain")*3.28084)+" ft ("+run.optString("elevation_source","Garmin")+")";
        if(!run.isNull("elevation_loss"))detail+="\nElevation loss: "+Math.round(Math.abs(run.optDouble("elevation_loss"))*3.28084)+" ft ("+run.optString("elevation_source","Garmin")+")";
        if(run.has("trial_error"))detail+="\n\n"+run.optString("trial_error");
        String category=run.optString("category");
        if(expandedChart!=null)expandedChart.dismiss();
        LinearLayout body=section();body.setPadding(dp(20),dp(8),dp(20),dp(28));
        addText(body,friendlyDate(run.optString("date")),14,muted,false,0);
        addText(body,run.optString("title"),28,ink,false,12);
        addText(body,ScatterPlot.label(category),14,muted,true,8);
        LinearLayout hero=section();hero.setPadding(dp(20),dp(20),dp(20),dp(20));hero.setBackground(shape(palette.primaryContainer,24));
        LinearLayout.LayoutParams heroLp=new LinearLayout.LayoutParams(-1,-2);heroLp.topMargin=dp(24);body.addView(hero,heroLp);
        addText(hero,"Recorded pace",14,palette.onPrimaryContainer,true,0);
        addText(hero,run.isNull("pace")?"—":ScatterPlot.pace(run.optDouble("pace"),miles),42,palette.onPrimaryContainer,false,8);
        addText(hero,miles?"minutes per mile":"minutes per kilometre",13,palette.onPrimaryContainer,false,4);
        addText(body,distanceText(run)+(run.isNull("duration")?"":" · "+raceTime(run.optDouble("duration"))+" duration"),20,ink,true,24);
        if(sessionAdjusted(run))addText(body,"Adjusted overall pace · "+paceValue(sessionPace(run,false))+(miles?" /mi":" /km")+"\n"+adjustmentLabel()+" where available",14,muted,false,12);
        if(intervalSession(run)&&Double.isFinite(run.optDouble("work_pace",Double.NaN))){
            addText(body,"Recorded work pace · "+paceValue(run.optDouble("work_pace"))+(miles?" /mi":" /km"),16,ink,false,12);
            if(sessionAdjusted(run))addText(body,"Adjusted work pace · "+paceValue(sessionPace(run,true))+(miles?" /mi":" /km"),14,muted,false,6);
        }
        if(!run.isNull("average_hr"))addText(body,"Average heart rate · "+Math.round(run.optDouble("average_hr"))+" bpm",16,ink,false,20);
        if(!run.isNull("hr_under_percent"))addText(body,Math.round(run.optDouble("hr_under_percent"))+"% of time below your HR ceiling · "+(run.optString("hr_source").contains("average")?"estimated from average HR":"recorded samples"),14,muted,false,8);
        if(effort!=null)addText(body,"Fastest continuous 5K · "+raceTime(effort.optDouble("duration")),18,ink,true,20);
        if(point!=null)addText(body,pointDescription(point,null,null,"trial".equals(point.optString("category"))||"prediction".equals(point.optString("category"))||"easy_prediction".equals(point.optString("category"))),14,muted,false,16);
        LinearLayout routePanel=section();routePanel.setPadding(dp(12),dp(12),dp(12),dp(12));routePanel.setBackground(shape(palette.container,20));
        LinearLayout.LayoutParams routeLp=new LinearLayout.LayoutParams(-1,-2);routeLp.topMargin=dp(20);body.addView(routePanel,routeLp);
        addText(routePanel,"GPS route",16,ink,true,0);
        RouteView routeView=new RouteView(this,palette);routeView.setVisibility(View.GONE);routePanel.addView(routeView,new LinearLayout.LayoutParams(-1,dp(210)));
        TextView routeStatus=addText(routePanel,"Loading route…",12,muted,false,6);
        Button retryRoute=actionButton("Retry route",false,()->{});retryRoute.setVisibility(View.GONE);routePanel.addView(retryRoute);
        LinearLayout more=section();addText(more,detail,14,muted,false,12);disclosure(body,"Recording & source details",more);
        final Dialog[] page={null};page[0]=fullScreen("Session",body,popup->{
            popup.getMenu().add("Change category").setEnabled(!busy).setOnMenuItemClickListener(item->{page[0].dismiss();chooseCategory(run);return true;});
            if(category.equals("short")||category.equals("medium")||category.equals("long"))popup.getMenu().add("Correct work laps").setEnabled(!busy).setOnMenuItemClickListener(item->{page[0].dismiss();chooseLaps(run);return true;});
        });
        java.util.concurrent.atomic.AtomicBoolean routeOpen=new java.util.concurrent.atomic.AtomicBoolean(true);
        page[0].setOnDismissListener(dialog->routeOpen.set(false));
        Runnable loadRoute=()->{
            routeStatus.setText("Loading route…");retryRoute.setVisibility(View.GONE);
            BackendRuntime.WORKER.execute(()->{
                if(!routeOpen.get())return;
                JSONObject data=null;try{data=invoke("route",run.optString("id"));}catch(Exception ignored){}
                final JSONObject result=data;
                runOnUiThread(()->{
                    if(isDestroyed()||!routeOpen.get())return;
                    if(result!=null&&result.optBoolean("ok")){
                        boolean available=routeView.setRoute(result.optJSONObject("route"));routeView.setVisibility(available?View.VISIBLE:View.GONE);
                        routeStatus.setText(available?"North up · ○ Start · ■ Finish":"No GPS route recorded for this session.");
                    }else{
                        routeStatus.setText("Couldn't load the route. Check your connection and try again.");retryRoute.setVisibility(View.VISIBLE);
                    }
                });
            });
        };
        retryRoute.setOnClickListener(view->loadRoute.run());loadRoute.run();
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
    private void startBackgroundSync(String operation){
        if(busy||!authenticated)return;
        try{
            String config=settings().toString();
            if(!foreground){SyncService.remember(this,operation,days,config);return;}
            requestSyncNotifications();
            syncLog.setLength(0);SyncService.start(this,operation,days,config);
        }catch(Exception error){message.setText("Couldn't start sync. Reopen the app and try again.");}
    }
    private void requestSyncNotifications(){
        if(android.os.Build.VERSION.SDK_INT>=33&&checkSelfPermission("android.permission.POST_NOTIFICATIONS")!=android.content.pm.PackageManager.PERMISSION_GRANTED
            &&!preferences.getBoolean("sync_notifications_asked",false)){
            preferences.edit().putBoolean("sync_notifications_asked",true).apply();
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},41);
        }
    }
    private void loadRuns(){loadDashboard(true);}
    private void loadDashboard(boolean refresh){
        if(busy)return;
        if(refresh){startBackgroundSync("dashboard");return;}
        execute("Opening saved charts…",()->invoke("cached_dashboard",LocalDate.now().toString(),days,settings().toString()),data->{
            profileDirty=false;renderRuns(data);restoreSavedScroll();
            JSONArray warnings=data.optJSONArray("warnings");
            message.setText("Saved data · "+data.optJSONArray("runs").length()+" sessions"+(warnings!=null&&warnings.length()>0?" · "+warnings.optString(0):""));
            resumeSyncIfNeeded();
            // On upgrade, recover an unfinished download started before service checkpoints existed.
            if(!busy&&authenticated&&!SyncService.hasRequestedSync(this)
                &&(!data.optBoolean("has_saved_data")||hasPendingDownloads(data)))loadDashboard(true);
            conditionsHandler.post(weatherAuto);
        });
    }
    private boolean hasPendingDownloads(JSONObject data){
        JSONObject sync=data.optJSONObject("sync");if(sync==null)return false;
        if(!sync.optBoolean("summaries_complete"))return true;
        String[] keys={"terrain","recovery","hr_recordings","interval_recordings","trial_recordings","weather"};
        String[] enabled={"include_terrain","include_recovery","include_recordings","include_recordings","","include_weather"};
        for(int i=0;i<keys.length;i++){
            JSONObject count=sync.optJSONObject(keys[i]);
            boolean use=enabled[i].isEmpty()||preferences.getBoolean(enabled[i],!enabled[i].equals("include_terrain"));
            if(use&&count!=null&&count.optInt("pending")>0)return true;
        }
        return false;
    }
    private void loadTerrain(){
        if(busy||!authenticated)return;
        preferences.edit().putBoolean("include_terrain",true).apply();
        startBackgroundSync("sync_terrain");
    }
    private void handleSampleRequest() {
        if(pendingSample==null||busy||!authenticated)return;
        Uri uri=pendingSample;pendingSample=null;
        if("rundashboard".equals(uri.getScheme())&&"terrain".equals(uri.getHost())){
            screen=PROFILE;profileOpen=true;syncDetailsOpen=true;renderProfile();message.setText("Tap Download / resume terrain to begin.");return;
        }
        if(!"rundashboard".equals(uri.getScheme())||!("sample".equals(uri.getHost())||"comparison".equals(uri.getHost())))return;
        final boolean comparison="comparison".equals(uri.getHost());
        final int port;final String token=uri.getQueryParameter("token");
        try{port=Integer.parseInt(uri.getQueryParameter("port"));}catch(Exception invalid){return;}
        if(port<1024||port>65535||token==null||!token.matches("[A-Za-z0-9_-]{24,128}"))return;
        new AlertDialog.Builder(this).setTitle(comparison?"Share a dashboard comparison?":"Share a training sample?")
            .setMessage(comparison?"Send saved activity titles, dates, pace, heart rate, sleep/recovery, weather, aggregate elevation, settings and chart values to the local comparison on this phone? Garmin credentials, session tokens and GPS routes are excluded. This reads saved data without downloading more.":"Send up to 20 run titles from the last year (prioritizing labeled 5K trials), dates, paces, lap summaries and fastest 5K summaries to the local development project on this phone? Credentials, session tokens, location and heart rate are excluded.")
            .setPositiveButton(comparison?"Share comparison":"Share sample",(dialog,which)->execute(comparison?"Preparing saved dashboard comparison…":"Preparing your training sample…",()-> {
                JSONObject result=comparison?invoke("comparison",LocalDate.now().toString(),days,settings().toString()):invoke("sample",LocalDate.now().toString());
                if(!result.optBoolean("ok"))return result;
                byte[] body=result.getJSONObject(comparison?"comparison":"sample").toString().getBytes(StandardCharsets.UTF_8);
                HttpURLConnection conn=(HttpURLConnection)new URL("http://127.0.0.1:"+port+(comparison?"/comparison/":"/sample/")+token).openConnection();
                conn.setConnectTimeout(10000);conn.setReadTimeout(30000);conn.setInstanceFollowRedirects(false);
                try {
                    conn.setRequestMethod("POST");conn.setDoOutput(true);conn.setRequestProperty("Content-Type","application/json");
                    try(java.io.OutputStream out=conn.getOutputStream()){out.write(body);}
                    if(conn.getResponseCode()!=200)throw new Exception("Local receiver unavailable");
                }finally{conn.disconnect();}
                return result;
            },result->message.setText(comparison?"Saved data shared. Open the comparison page for the report.":"Training sample shared with the local project.")))
            .setNegativeButton("Cancel",null).show();
    }
    private void logout() {
        execute("Signing out…",()->{store.clear();SyncService.clear(this);dashboardData=null;preferences.edit().remove("settings").apply();return invoke("logout");},result->{profileOpen=true;screen=PROFILE;render(result);message.setText("Signed out. Your saved session was removed.");});
    }
    private JSONObject invoke(String operation,Object... args) throws Exception {
        return BackendRuntime.invoke(getApplicationContext(),operation,args);
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
        if(refreshButton!=null)refreshButton.setContentDescription("Open sync controls");
        downloadProgress.setVisibility(View.VISIBLE);downloadProgress.setIndeterminate(true);
        syncLog.setLength(0);recordProgress(status);
        message.setTextColor(muted);message.setText(status);
        BackendRuntime.WORKER.execute(()-> {
            JSONObject result=null;String error=null;
            try {result=work.run();} catch(Throwable failure) {error="Couldn't start or complete the request. Reopen the app and try again.";}
            final JSONObject data=result;final String failure=error;
            runOnUiThread(()-> {
                if(isDestroyed())return;
                syncRunning=false;getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                busy=false;enable(content,true);updateChrome();downloadProgress.setVisibility(View.GONE);
                if(refreshButton!=null)refreshButton.setContentDescription("Sync training data");
                if(failure!=null || data==null || !data.optBoolean("ok")) {
                    if(data!=null && !data.optBoolean("authenticated") && !authenticated) render(data);
                    recordProgress(failure!=null?failure:data==null?"Could not complete the request.":data.optString("error"));
                    message.setTextColor(palette.error);message.setText(failure!=null?failure:data==null?"Could not complete the request.":data.optString("error"));
                } else {recordProgress("Dashboard ready.");message.setText("");done.accept(data);}
                handleSampleRequest();
            });
        });
    }
}
