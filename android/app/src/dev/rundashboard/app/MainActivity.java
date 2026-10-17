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
    private TextView heading;
    private final MaterialUi.NavigationItem[] tabs=new MaterialUi.NavigationItem[SCREEN_COUNT];
    private int screen, visibleRuns=30;
    private final int[] scrollPositions=new int[SCREEN_COUNT];
    private String runFilter="all", query="";
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
        preferences=getSharedPreferences("training",0);
        palette=MaterialUi.palette(this);ink=palette.ink;muted=palette.muted;
        setTheme(getResources().getIdentifier(palette.dark?"Theme.RunDashboard.Dark":"Theme.RunDashboard.Light","style",getPackageName()));
        super.onCreate(state);
        if(state!=null){restoreScroll=true;screen=state.getInt("screen",TRENDS);profileOpen=screen==PROFILE;runFilter=state.getString("run_filter","all");query=state.getString("query","");int[] positions=state.getIntArray("scroll_positions");if(positions!=null)System.arraycopy(positions,0,scrollPositions,0,Math.min(positions.length,SCREEN_COUNT));}
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_SECURE,WindowManager.LayoutParams.FLAG_SECURE);
        getWindow().setStatusBarColor(palette.surface);
        getWindow().setNavigationBarColor(palette.container);
        getWindow().getDecorView().setSystemUiVisibility(palette.dark?0:View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        store=new SessionStore(getApplicationContext());
        preferences=getSharedPreferences("training",0);
        if(!preferences.getBoolean("ux_defaults_v1",false)){
            android.content.SharedPreferences.Editor defaults=preferences.edit().putBoolean("ux_defaults_v1",true);
            if(preferences.getInt("days",0)==0)defaults.putInt("days",90);
            defaults.apply();
        }
        days=preferences.getInt("days",90);miles=preferences.getBoolean("miles",true);
        pendingSample=getIntent().getData();
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(palette.surface);setContentView(root);
        root.setOnApplyWindowInsetsListener((view,insets)-> {
            view.setPadding(0,insets.getSystemWindowInsetTop(),0,insets.getSystemWindowInsetBottom());
            return insets.consumeSystemWindowInsets();
        });
        LinearLayout header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(dp(20),dp(6),dp(12),dp(6));header.setMinimumHeight(dp(64));
        heading=text("Trends",24,ink,false);header.addView(heading,new LinearLayout.LayoutParams(0,-2,1));
        refreshButton=iconButton(MaterialUi.Icon.SYNC,"Sync training data",this::showSyncSheet);
        header.addView(refreshButton,new LinearLayout.LayoutParams(dp(48),dp(48)));root.addView(header);
        rangeBar=new MaterialUi.ButtonGroup(this,false);rangeBar.setPadding(dp(20),0,dp(20),dp(8));rangeArea=rangeBar;root.addView(rangeBar,new LinearLayout.LayoutParams(-1,-2));
        adjustBar=new LinearLayout(this);adjustBar.setVisibility(View.GONE);
        scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setClipToPadding(false);
        content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(20),dp(8),dp(20),dp(24));scroll.addView(content);
        root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
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
        for(int i=0;i<tabs.length;i++){
            final int tab=i;tabs[i]=new MaterialUi.NavigationItem(this,names[i],i,palette);
            tabs[i].setOnClickListener(v->selectScreen(tab));navigation.addView(tabs[i],new LinearLayout.LayoutParams(0,-2,1));
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
    @Override protected void onResume(){super.onResume();foreground=true;resumeSyncIfNeeded();}
    @Override protected void onPause(){foreground=false;super.onPause();}
    @Override protected void onStop(){SyncService.unlisten(syncListener);super.onStop();}
    @Override protected void onDestroy(){SyncService.unlisten(syncListener);super.onDestroy();}
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
        LinearLayout panel=new LinearLayout(this);panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(20),dp(20),dp(20),dp(20));panel.setBackground(panelShape());
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.bottomMargin=dp(16);content.addView(panel,lp);return panel;
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
    private void segmented(LinearLayout parent,String[] labels,int selected,java.util.function.IntConsumer choose){
        MaterialUi.ButtonGroup group=new MaterialUi.ButtonGroup(this,true);
        for(int i=0;i<labels.length;i++){
            final int option=i;Button control=chipButton(labels[i],selected==i,()->choose.accept(option));control.setTextSize(13);control.setPadding(dp(8),dp(8),dp(8),dp(8));
            control.setAccessibilityDelegate(new View.AccessibilityDelegate(){@Override public void onInitializeAccessibilityNodeInfo(View host,android.view.accessibility.AccessibilityNodeInfo info){super.onInitializeAccessibilityNodeInfo(host,info);info.setClassName("android.widget.RadioButton");info.setCheckable(true);info.setChecked(option==selected);}});
            group.addView(control);
        }
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(12);parent.addView(group,lp);
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
        heading.setText(new String[]{"Trends","Sessions","Interval targets","Profile"}[screen]);
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
        if(screen==TRENDS){
            int count=(adjusted("adjust_elevation")?1:0)+(adjusted("adjust_temperature")?1:0);
            Button adjustments=chipButton(count==0?"Adjustments ▾":"Adjustments · "+count+" ▾",count>0,this::editAdjustments);adjustments.setEnabled(!busy);
            adjustments.setContentDescription("Pace adjustments. "+adjustmentLabel()+". Open options.");
            rangeBar.addView(adjustments);
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
                execute("Verifying your code…",()->invoke("verify",value),result->{code.setText("");render(result);if(authenticated){profileOpen=false;screen=TRENDS;renderRuns(null);loadRuns();}});
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
                execute("Signing in to Garmin. This may take a minute…",()->{store.clear();SyncService.clear(this);return invoke("login",user,pass);},result->{render(result);if(authenticated){profileOpen=false;screen=TRENDS;renderRuns(null);loadRuns();}});
            });
            addText(parent,"Your password goes to Garmin over HTTPS and isn't saved. Your session is encrypted on this phone. Personal prototype using an unofficial Garmin connection.",12,muted,false,20);
        }
    }
    @Override public void onBackPressed(){
        if(screen!=TRENDS){selectScreen(TRENDS);return;}
        super.onBackPressed();
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
        addText(display,"Interval points",14,muted,true,20);
        boolean average="session".equals(setting("interval_mode","session"));
        segmented(display,new String[]{"Repetitions","Session average"},average?1:0,choice->{String mode=choice==1?"session":"rep";if(!mode.equals(setting("interval_mode","session"))){preferences.edit().putString("interval_mode",mode).apply();profileDirty=true;renderProfile();}});
        addText(display,"5K times always use minutes:seconds.",12,muted,false,16);
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
    private String adjustmentLabel(){
        return adjusted("adjust_elevation")?(adjusted("adjust_temperature")?"Elevation + weather":"Elevation"):(adjusted("adjust_temperature")?"Weather":"No condition adjustments");
    }
    private void editAdjustments(){
        LinearLayout form=section();addText(form,"Show equivalent pace for flat or cool conditions where measurements are available. Recorded values remain available in point details.",14,muted,false,8);
        Switch elevation=new Switch(this),weather=new Switch(this);elevation.setText("Elevation");weather.setText("Weather · temperature / dew point");
        elevation.setTextColor(ink);weather.setTextColor(ink);elevation.setMinHeight(dp(64));weather.setMinHeight(dp(64));elevation.setChecked(adjusted("adjust_elevation"));weather.setChecked(adjusted("adjust_temperature"));
        form.addView(elevation,new LinearLayout.LayoutParams(-1,-2));form.addView(weather,new LinearLayout.LayoutParams(-1,-2));
        bottomSheet("Pace adjustments",form,"Apply adjustments",dialog->{saveSetting("adjust_elevation",elevation.isChecked());saveSetting("adjust_temperature",weather.isChecked());dialog.dismiss();loadDashboard(false);});
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
            boolean average="session".equals(setting("interval_mode","session"));
            chartCard("Interval pace",average?"Session averages":"Work repetitions",data.optJSONArray("interval_points"),false,new String[]{"short","medium","long"});
            chartCard("Easy pace","Road, treadmill and trail",data.optJSONArray("run_points"),false,new String[]{"easy"});heartCard();
        }else if("load".equals(selected))weeklyCard();
        else if("recovery".equals(selected))recoveryCard();
        else predictionCard();
        recentSessions();
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
    private void chartLegend(LinearLayout panel,String[] labels,String[] categories,int[] markers){
        MaterialUi.ButtonGroup row=new MaterialUi.ButtonGroup(this,false);row.setPadding(0,dp(12),0,dp(4));
        for(int i=0;i<labels.length;i++){
            TextView item=text(labels[i],12,muted,false);item.setPadding(0,dp(4),dp(4),dp(4));
            MaterialUi.Marker marker=new MaterialUi.Marker(markers[i],palette.chart(ScatterPlot.color(categories[i])));marker.setBounds(0,0,dp(14),dp(14));
            item.setCompoundDrawables(marker,null,null,null);item.setCompoundDrawablePadding(dp(4));row.addView(item);
        }
        panel.addView(row,new LinearLayout.LayoutParams(-1,-2));
    }
    private void predictionOptions(){
        LinearLayout body=section();RadioGroup mode=chartChoices(body,"Compare pace",new String[]{"Recorded effort","HR-adjusted effort"},"intensity".equals(setting("prediction_mode","observed"))?1:0);
        addText(body,"Visible series",14,ink,true,16);String[] keys={"trial_points","prediction_points","easy_prediction_points"},labels={"Measured 5K","Interval estimate","Easy estimate"};
        CheckBox[] choices=new CheckBox[keys.length];
        for(int i=0;i<keys.length;i++){CheckBox choice=new CheckBox(this);choice.setText(labels[i]);choice.setTextSize(15);choice.setTextColor(ink);choice.setMinHeight(dp(48));choice.setChecked(preferences.getBoolean("show_"+keys[i],true));body.addView(choice,new LinearLayout.LayoutParams(-1,-2));choices[i]=choice;}
        addText(body,"Measured points come from recorded 5K efforts. Dashed lines are calibrated estimates. Easy estimates need at least two nearby trials. Missing condition data stays unadjusted.",14,muted,false,12);
        bottomSheet("5K chart settings",body,"Apply",dialog->{
            boolean any=false;for(CheckBox choice:choices)any|=choice.isChecked();if(!any){Toast.makeText(this,"Choose at least one series",Toast.LENGTH_SHORT).show();return;}
            for(int i=0;i<keys.length;i++)preferences.edit().putBoolean("show_"+keys[i],choices[i].isChecked()).apply();
            saveSetting("prediction_mode",checkedChoice(mode)==1?"intensity":"observed");dialog.dismiss();loadDashboard(false);
        });
    }
    private void paceOptions(boolean easy){
        LinearLayout body=section();String key=easy?"easy_mode":"interval_pace_mode";
        RadioGroup mode=chartChoices(body,"Compare pace",new String[]{"Recorded effort","HR-adjusted effort"},"intensity".equals(setting(key,"observed"))?1:0);
        RadioGroup scale=easy?chartChoices(body,"Pace scale",new String[]{"Fit to all measurements","Fixed 7:00–10:00 min/mile"},preferences.getBoolean("easy_auto_scale",true)?0:1):null;
        RadioGroup intervals=easy?null:chartChoices(body,"Interval points",new String[]{"Session averages","Individual work repetitions"},"session".equals(setting("interval_mode","session"))?0:1);
        bottomSheet(easy?"Easy pace settings":"Interval pace settings",body,"Apply",dialog->{
            saveSetting(key,checkedChoice(mode)==1?"intensity":"observed");
            if(easy)preferences.edit().putBoolean("easy_auto_scale",checkedChoice(scale)==0).apply();
            else{String value=checkedChoice(intervals)==0?"session":"rep";preferences.edit().putString("interval_mode",value).apply();saveSetting("interval_mode",value);}
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
        String[] names={"Measured","Intervals","Easy"},categories={"trial","prediction","easy_prediction"};int[] markers={1,2,3};
        java.util.ArrayList<String> visibleNames=new java.util.ArrayList<>(),visibleCategories=new java.util.ArrayList<>();java.util.ArrayList<Integer> visibleMarkers=new java.util.ArrayList<>();
        for(int i=0;i<keys.length;i++)if(preferences.getBoolean("show_"+keys[i],true)){
            JSONArray source=dashboardData.optJSONArray(keys[i]);if(source!=null)for(int j=0;j<source.length();j++)points.put(source.optJSONObject(j));
            visibleNames.add(names[i]);visibleCategories.add(categories[i]);visibleMarkers.add(markers[i]);
        }
        int[] shapes=new int[visibleMarkers.size()];for(int i=0;i<shapes.length;i++)shapes[i]=visibleMarkers.get(i);
        chartLegend(panel,visibleNames.toArray(new String[0]),visibleCategories.toArray(new String[0]),shapes);
        addText(panel,"Dashed lines are estimates · "+adjustmentLabel()+("intensity".equals(setting("prediction_mode","observed"))?" · HR-adjusted effort":""),12,muted,false,4);
        addInteractivePlot(panel,"5K performance",points,null,null,Double.NaN,true,false,false);
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
        chartLegend(panel,new String[]{"≥90% below","75–89%","<75%"},new String[]{"easy","cross_train","trial"},new int[]{0,0,0});
        addInteractivePlot(panel,"Easy effort",points,average?"average_hr":"hr_under_percent",average?"AVERAGE HR · BPM":"TIME BELOW CEILING · %",average?preferences.getInt("easy_hr",134):Double.NaN,false,false,false);
    }
    private void chartCard(String title,String subtitle,JSONArray points,boolean trial,String[] categories){
        boolean easy=categories.length==1&&"easy".equals(categories[0]);
        LinearLayout panel=card();chartHeader(panel,title,()->paceOptions(easy));
        JSONObject latest=latestPoint(points);
        if(latest!=null){addText(panel,ScatterPlot.pace(latest.optDouble("pace"),miles)+(miles?" /mi":" /km"),32,ink,false,8);addText(panel,"Latest plotted pace · "+latest.optString("date"),13,muted,false,2);}
        if(easy)chartLegend(panel,new String[]{"Road / treadmill","Trail"},new String[]{"easy","easy"},new int[]{0,4});
        else chartLegend(panel,new String[]{"Short","Medium","Long"},categories,new int[]{2,3,0});
        addText(panel,(easy?"Shading: typical pace range":subtitle)+" · "+adjustmentLabel()+("intensity".equals(setting(easy?"easy_mode":"interval_pace_mode","observed"))?" · HR-adjusted effort":""),12,muted,false,4);
        addInteractivePlot(panel,title,points,null,null,Double.NaN,trial,easy&&!preferences.getBoolean("easy_auto_scale",true),false);
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
            raw=point.optInt("lap")>0?point.optDouble("duration")/point.optDouble("distance")*1000:run==null?point.optDouble("work_pace"):run.optDouble("work_pace");
        }
        double shown=point.optDouble("pace");String unit=miles?" /mi":" /km";
        String mode=setting((category.equals("easy")||category.equals("easy_long"))?"easy_mode":"interval_pace_mode","observed");
        String adjustments=adjustmentLabel()+(mode.equals("intensity")?" · HR-adjusted effort":"");
        return heading+"\nRecorded pace "+ScatterPlot.pace(raw,miles)+unit+"\nShown pace "+ScatterPlot.pace(shown,miles)+unit+"\n"+adjustments+" where available"+(point.optInt("lap")>0?" · work lap "+point.optInt("lap"):"");
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
    private void addInteractivePlot(LinearLayout panel,String title,JSONArray input,String key,String label,double reference,boolean trial,boolean fixedEasy,boolean expanded){
        final JSONArray points=new JSONArray();
        if(input!=null)for(int i=0;i<input.length();i++){
            JSONObject point=input.optJSONObject(i);if(point==null)continue;double value=point.optDouble(key!=null?key:trial?"duration":"pace",Double.NaN);
            if(Double.isFinite(value)&&(key!=null||value>0))points.put(point);
        }
        if(points.length()==0){addText(panel,"No matching measurements in this date range.",15,muted,false,16);return;}
        final boolean weekly=points.optJSONObject(0).optBoolean("bar");
        String start=dashboardData.optString("start");if(weekly)start=LocalDate.parse(start).minusDays(6).toString();
        if(expanded){addText(panel,dateSpan(dashboardData.optString("start"),dashboardData.optString("end")),14,ink,false,0);addText(panel,"Pinch to zoom · drag when zoomed · double-tap to reset",13,muted,false,8);}
        ScatterPlot plot=new ScatterPlot(this,points,start,dashboardData.optString("end"),miles,trial,fixedEasy,key,label,reference,point->showPointSheet(weekly?"Week details":"Point details",point,key,label,trial));
        plot.setExplorationEnabled(expanded);int height=chartHeight(expanded?360:240);panel.addView(plot,new LinearLayout.LayoutParams(-1,height));
        if(fixedEasy){int outside=0;for(int i=0;i<points.length();i++){double pace=points.optJSONObject(i).optDouble("pace")*1.609344;if(pace<420||pace>600)outside++;}if(outside>0)addText(panel,outside+" runs outside this fixed scale. Choose Fit to all measurements in chart settings to include them.",14,muted,false,4);}
        addText(panel,weekly?"Tap a bar for its week's details":"Tap a point for details",12,muted,false,6);
        MaterialUi.ButtonGroup actions=new MaterialUi.ButtonGroup(this,true);actions.setPadding(0,dp(12),0,0);panel.addView(actions,new LinearLayout.LayoutParams(-1,-2));
        if(!expanded){actions.addView(actionButton("Explore chart",false,()->expandPlot(title,points,key,label,reference,trial,fixedEasy)));return;}
        actions.addView(actionButton("View data",false,()->{
            String[] rows=new String[points.length()];for(int i=0;i<rows.length;i++)rows[i]=pointDescription(points.optJSONObject(i),key,label,trial);
            chartData(title,rows,w->plot.selectPoint(points.optJSONObject(w)));
        }));
        Button reset=actionButton("Reset zoom",false,plot::resetZoom);actions.addView(reset);reset.setVisibility(View.GONE);
        Button filter=button(panel,"Use visible dates across app",false,()->applyChartRange(plot.visibleDates()));filter.setVisibility(View.GONE);
        plot.setViewportListener(()->{boolean zoomed=plot.isZoomed();reset.setVisibility(zoomed?View.VISIBLE:View.GONE);filter.setVisibility(zoomed?View.VISIBLE:View.GONE);});
    }
    private void expandPlot(String title,JSONArray points,String key,String label,double reference,boolean trial,boolean fixedEasy){
        LinearLayout panel=section();panel.setPadding(dp(16),dp(12),dp(16),dp(20));
        addInteractivePlot(panel,title,points,key,label,reference,trial,fixedEasy,true);showExpanded(title,panel);
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
        addInteractivePlot(panel,"Weekly training",points,"value",axis,Double.NaN,false,false,false);
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
        if(expanded){addText(panel,dateSpan(dashboardData.optString("start"),dashboardData.optString("end")),14,ink,false,0);addText(panel,"Pinch to zoom dates · drag when zoomed · double-tap to reset",13,muted,false,8);}
        RecoveryPlot plot=new RecoveryPlot(this,weeks,metric,point->{LinearLayout body=section();addText(body,recoveryDescription(point),16,ink,false,12).setTextIsSelectable(true);openPointSheet("Recovery details",body);});
        plot.setExplorationEnabled(expanded);panel.addView(plot,new LinearLayout.LayoutParams(-1,chartHeight(metric.equals("all")?420:expanded?360:240)));
        addText(panel,"Tap a measurement for its value and measured days",12,muted,false,6);
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
    private void recentSessions(){
        LinearLayout panel=card();addText(panel,"Recent sessions",20,ink,true,0);addText(panel,"Latest activities in the selected range",12,muted,false,4);
        String[] keys={"all","easy","easy_long","short","medium","long","trial","warmup","rebuild_run","cross_train","cross_interval","strength","other_run","other"};
        String[] labels=new String[keys.length];labels[0]="All types";for(int i=1;i<keys.length;i++)labels[i]=ScatterPlot.label(keys[i]);
        String filter=setting("recent_filter","all");smallButton(panel,(filter.equals("all")?"All types":ScatterPlot.label(filter))+" ▾",()->chooseMode("Session type","recent_filter",labels,keys));
        JSONArray rows=dashboardData.optJSONArray("runs");int shown=0;
        if(rows!=null)for(int i=0;i<rows.length()&&shown<3;i++){
            JSONObject run=rows.optJSONObject(i);if(!filter.equals("all")&&!filter.equals(run.optString("category")))continue;shown++;
            LinearLayout item=new LinearLayout(this);item.setOrientation(LinearLayout.VERTICAL);item.setPadding(0,dp(14),0,dp(14));
            addText(item,run.optString("date")+" · "+ScatterPlot.label(run.optString("category")),13,ink,true,0);
            addText(item,run.optString("title"),15,ink,true,5);addText(item,sessionMetrics(run),12,muted,false,5);
            item.setOnClickListener(v->{if(!busy)showRun(run);});panel.addView(item,new LinearLayout.LayoutParams(-1,-2));
            View divider=new View(this);divider.setBackgroundColor(palette.outline);panel.addView(divider,new LinearLayout.LayoutParams(-1,dp(1)));
        }
        if(shown==0)addText(panel,"No sessions of this type.",14,muted,false,14);
        button(panel,"All sessions →",false,()->{runFilter=filter;selectScreen(SESSIONS);});
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
    private String targetConditionsLabel(){
        String temperature=setting("target_temperature","45"),humidity=setting("target_humidity","");
        String gain=setting("target_gain","0"),loss=setting("target_loss","0");
        boolean flat=(gain.isEmpty()||"0".equals(gain))&&(loss.isEmpty()||"0".equals(loss));
        return (temperature.isEmpty()?"No temperature":temperature+"°F")+(humidity.isEmpty()?"":" · "+humidity+"% humidity")+" · "+(flat?"Flat":"+"+gain+" / −"+loss+" ft");
    }
    private void renderTargets(){
        addText(content,"Your next interval session",26,ink,false,0);
        addText(content,"Choose a 5K basis, then set the conditions you’ll run in.",14,muted,false,6);
        LinearLayout basis=card();String source=setting("target_source","predicted");
        String[] values={"predicted","latest","custom"};int selected=source.equals("custom")?2:source.equals("latest")?1:0;
        addText(basis,"5K basis",16,ink,true,0);
        segmented(basis,new String[]{"Estimate","Latest trial","Custom"},selected,choice->{if(!values[choice].equals(source)){saveSetting("target_source",values[choice]);loadDashboard(false);}});
        JSONObject targets=dashboardData.optJSONObject("targets");
        boolean valid=targets!=null&&!targets.has("error")&&source.equals(targets.optString("source"));
        if(source.equals("custom")){
            EditText custom=input(basis,"Custom 5K time · mm:ss",InputType.TYPE_CLASS_TEXT);custom.setHint("20:00");custom.setText(setting("target_time",""));
            button(basis,"Update targets",true,()->{String value=custom.getText().toString().trim();if(!validTargetTime(value)){custom.setError("Use mm:ss between 5:00 and 120:00");return;}saveSetting("target_time",value);custom.clearFocus();((android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(custom.getWindowToken(),0);loadDashboard(false);});
        }
        addText(basis,valid?raceTime(targets.optDouble("seconds"))+" for 5K · "+(source.equals("custom")?"your time":source.equals("latest")?"latest measured trial":"calibrated interval estimate"):
            targets==null?"Sync your training data to calculate targets.":targets.optString("error","Updating your 5K basis…"),14,valid?muted:palette.error,false,12);
        if(!source.equals("custom"))addText(basis,"Your full-history setting controls the calibration available for this basis.",12,muted,false,6);
        LinearLayout.LayoutParams basisLp=(LinearLayout.LayoutParams)basis.getLayoutParams();basisLp.topMargin=dp(20);basis.setLayoutParams(basisLp);
        LinearLayout conditions=section();
        Button condition=chipButton("Conditions · "+targetConditionsLabel()+" ▾",false,this::editTargetConditions);condition.setGravity(Gravity.START|Gravity.CENTER_VERTICAL);condition.setContentDescription("Target conditions. "+targetConditionsLabel()+". Edit conditions.");conditions.addView(condition,new LinearLayout.LayoutParams(-1,-2));
        LinearLayout.LayoutParams conditionsLp=new LinearLayout.LayoutParams(-1,-2);conditionsLp.bottomMargin=dp(16);content.addView(conditions,conditionsLp);
        if(!valid){LinearLayout empty=card();addText(empty,"A pace for every repetition",22,ink,false,0);addText(empty,"Select Custom to enter a 5K time, or sync a measured trial and interval history.",15,muted,false,10);return;}
        JSONArray rows=targets.optJSONArray("rows");LinearLayout calculations=section();
        if(rows!=null)for(int i=0;i<rows.length();i++){
            JSONObject row=rows.optJSONObject(i);String category=row.optString("category");LinearLayout pace=card();
            boolean featured=i==0;pace.setBackground(shape(featured?palette.primaryContainer:palette.container,24));
            int foreground=featured?palette.onPrimaryContainer:ink;
            LinearLayout title=new LinearLayout(this);title.setGravity(Gravity.CENTER_VERTICAL);boolean largeText=getResources().getConfiguration().fontScale>1.3f;if(largeText)title.setOrientation(LinearLayout.VERTICAL);
            TextView name=text(category.substring(0,1).toUpperCase(Locale.getDefault())+category.substring(1),18,foreground,true);title.addView(name,largeText?new LinearLayout.LayoutParams(-1,-2):new LinearLayout.LayoutParams(0,-2,1));
            TextView reps=text(row.optString("reps"),14,foreground,false);title.addView(reps);pace.addView(title);
            TextView value=addText(pace,ScatterPlot.pace(row.optDouble("pace"),miles),44,foreground,false,10);value.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));value.setMaxLines(1);value.setAutoSizeTextTypeUniformWithConfiguration(28,44,1,android.util.TypedValue.COMPLEX_UNIT_SP);
            addText(pace,miles?"minutes per mile":"minutes per kilometre",13,foreground,false,2);
            addText(calculations,ScatterPlot.label(category)+": base "+ScatterPlot.pace(row.optDouble("base_pace"),miles)+String.format(Locale.getDefault()," · conditions %+.0f s/%s",row.optDouble("delta")*(miles?1.609344:1),miles?"mi":"km"),14,muted,false,12);
        }
        LinearLayout equivalent=card();addText(equivalent,"Equivalent race times",20,ink,false,0);
        LinearLayout races=section();JSONArray entries=targets.optJSONArray("races");
        if(entries!=null)for(int i=0;i<entries.length();i++){
            JSONObject row=entries.optJSONObject(i);LinearLayout line=new LinearLayout(this);line.setGravity(Gravity.CENTER_VERTICAL);line.setPadding(0,dp(12),0,dp(12));boolean largeText=getResources().getConfiguration().fontScale>1.3f;if(largeText)line.setOrientation(LinearLayout.VERTICAL);
            TextView distance=text(row.optString("label"),15,ink,false);line.addView(distance,largeText?new LinearLayout.LayoutParams(-1,-2):new LinearLayout.LayoutParams(0,-2,1));
            TextView time=text(raceTime(row.optDouble("duration")),20,ink,true);line.addView(time);races.addView(line);
            addText(races,ScatterPlot.pace(row.optDouble("pace"),miles)+(miles?" /mi":" /km"),13,muted,false,0);
        }
        smallButton(races,"Add a race distance",this::editRaceDistance);disclosure(equivalent,"View predictions",races);
        LinearLayout explanation=card();addText(explanation,"About these targets",20,ink,false,0);
        addText(calculations,String.format(Locale.getDefault(),"Performance index (FVDOT): %.1f",targets.optDouble("vdot")),14,muted,false,12);
        addText(calculations,"Targets use your chosen 5K basis and entered conditions. Elevation uses the latest matching interval distance, then workout distance. Without a matching distance, elevation stays unadjusted.",14,muted,false,12);
        disclosure(explanation,"Calculation details",calculations);
    }
    private String raceTime(double value){long seconds=Math.round(value);return seconds>=3600?String.format(Locale.getDefault(),"%d:%02d:%02d",seconds/3600,seconds/60%60,seconds%60):ScatterPlot.pace(value,false);}
    private boolean validTargetTime(String value){
        try{String[] parts=value.split(":",-1);if(parts.length<2||parts.length>3)return false;long seconds=0;for(int i=0;i<parts.length;i++){if(!parts[i].matches("[0-9]+"))return false;int part=Integer.parseInt(parts[i]);if(i>0&&part>=60)return false;seconds=seconds*60+part;}return seconds>=300&&seconds<=7200;}catch(Exception e){return false;}
    }
    private void editTargetConditions(){
        LinearLayout form=section();
        addText(form,"Target paces account for these conditions. Trend adjustments are set separately in Trends.",14,muted,false,8);
        String[] keys={"target_temperature","target_humidity","target_gain","target_loss"},labels={"Temperature · °F","Humidity · % (optional)","Elevation gain · ft","Elevation loss · ft"},defaults={"45","","0","0"};EditText[] fields=new EditText[keys.length];
        for(int i=0;i<fields.length;i++){fields[i]=input(form,labels[i],InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_DECIMAL|InputType.TYPE_NUMBER_FLAG_SIGNED);fields[i].setText(setting(keys[i],defaults[i]));}
        bottomSheet("Running conditions",form,"Apply conditions",dialog->{
            for(int i=0;i<fields.length;i++){String value=fields[i].getText().toString().trim();if(value.isEmpty())continue;try{double n=Double.parseDouble(value);if(!Double.isFinite(n)||(i==1&&(n<0||n>100))||(i>=2&&n<0))throw new NumberFormatException();}catch(NumberFormatException error){fields[i].setError("Enter a valid value");return;}}
            for(int i=0;i<fields.length;i++)saveSetting(keys[i],fields[i].getText().toString().trim());dialog.dismiss();loadDashboard(false);
        });
    }
    private void editRaceDistance(){
        LinearLayout form=section();EditText distance=input(form,"Extra race distance · "+(miles?"miles":"km")+" (optional)",InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_DECIMAL);
        String saved=setting("race_distance_miles","");if(!miles&&!saved.isEmpty())try{saved=String.format(Locale.ROOT,"%.3f",Double.parseDouble(saved)*1.609344);}catch(Exception ignored){}distance.setText(saved);
        bottomSheet("Race distance",form,"Save distance",dialog->{
            String value=distance.getText().toString().trim();try{if(!value.isEmpty()){double n=Double.parseDouble(value)/(miles?1:1.609344);if(!Double.isFinite(n)||n<=0||n>200)throw new NumberFormatException();value=Double.toString(n);}}catch(NumberFormatException error){distance.setError("Use a distance above 0 and up to "+(miles?"200 miles":"321.9 km"));return;}
            saveSetting("race_distance_miles",value);dialog.dismiss();loadDashboard(false);
        });
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
        addText(content,"Find a session",26,ink,false,0);
        EditText search=new EditText(this);search.setSingleLine(true);search.setTextSize(15);search.setTextColor(ink);
        search.setHint("Search session titles");search.setHintTextColor(muted);search.setPadding(dp(14),0,dp(14),0);search.setBackground(shape(palette.high,28));
        search.setMinimumHeight(dp(56));search.setInputType(InputType.TYPE_CLASS_TEXT);search.setText(query);LinearLayout.LayoutParams searchLp=new LinearLayout.LayoutParams(-1,-2);searchLp.topMargin=dp(16);content.addView(search,searchLp);
        HorizontalScrollView filters=new HorizontalScrollView(this);filters.setHorizontalScrollBarEnabled(false);
        LinearLayout chips=new LinearLayout(this);String[] keys={"all","attention","easy","easy_long","short","medium","long","trial","cross_train","cross_interval","strength","warmup","rebuild_run","other_run","other"};
        String[] labels={"All","Needs review","Easy","Easy Long","Short","Medium","Long","5K","Cross-training","Cross intervals","Strength","Warmup","Rebuild","Other run","Other"};int selected=0;
        for(int i=0;i<keys.length;i++){
            final String key=keys[i];if(key.equals(runFilter))selected=i;
            Button chip=chipButton(labels[i],key.equals(runFilter),()->{runFilter=key;visibleRuns=30;renderRuns(null);});chip.setTextSize(12);
            LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-2,-2);lp.rightMargin=dp(6);chips.addView(chip,lp);
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
    private void renderRunList(){
        runList.removeAllViews();JSONArray runs=dashboardData.optJSONArray("runs");int matching=0;String lastDate="";
        if(runs!=null)for(int i=0;i<runs.length();i++){
            JSONObject run=runs.optJSONObject(i);if(run==null)continue;
            if(!run.optString("title").toLowerCase(Locale.ROOT).contains(query.toLowerCase(Locale.ROOT)))continue;
            if("attention".equals(runFilter)?!needsReview(run):!"all".equals(runFilter)&&!runFilter.equals(run.optString("category")))continue;
            matching++;if(matching>visibleRuns)continue;
            String day=run.optString("date");
            if(!day.equals(lastDate)){addText(runList,friendlyDate(day),14,muted,true,24);lastDate=day;}
            LinearLayout row=section();row.setPadding(dp(16),dp(16),dp(16),dp(16));row.setBackground(MaterialUi.ripple(this,palette.container,20,palette.primary));row.setMinimumHeight(dp(112));row.setFocusable(true);
            String category=run.optString("category");
            TextView type=addText(row,ScatterPlot.label(category),12,muted,true,0);GradientDrawable marker=shape(palette.chart(ScatterPlot.color(category)),6);marker.setBounds(0,0,dp(10),dp(10));type.setCompoundDrawables(marker,null,null,null);type.setCompoundDrawablePadding(dp(6));
            TextView title=addText(row,run.optString("title"),18,ink,true,6);title.setMaxLines(2);title.setEllipsize(TextUtils.TruncateAt.END);
            addText(row,displayPace(run)+" · "+distanceText(run)+(run.isNull("duration")?"":" · "+raceTime(run.optDouble("duration"))),14,ink,false,10);
            if(!run.isNull("average_hr"))addText(row,Math.round(run.optDouble("average_hr"))+" bpm average"+(run.has("best_5k")?" · 5K "+raceTime(run.optJSONObject("best_5k").optDouble("duration")):""),12,muted,false,6);
            if(needsReview(run))addText(row,"Needs review · open session actions",12,palette.error,false,8);
            row.setContentDescription(run.optString("title")+", "+day+", "+ScatterPlot.label(category)+", "+sessionMetrics(run)+". Open session details.");
            row.setOnClickListener(v->{if(!busy)showRun(run);});LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(8);runList.addView(row,lp);
        }
        if(matching==0)addText(runList,"No sessions match. Try another filter or date range.",15,muted,false,24);
        else{addText(runList,matching+" matching sessions",12,muted,false,16);if(matching>visibleRuns){Button more=actionButton("Show more sessions",false,()->{visibleRuns+=30;renderRunList();});LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(12);runList.addView(more,lp);}}
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
        if(run.has("work_source"))detail+="\nWork metrics: "+run.optString("work_source");
        if(!run.isNull("elevation_gain"))detail+="\nElevation gain: "+Math.round(run.optDouble("elevation_gain")*3.28084)+" ft ("+run.optString("elevation_source","Garmin")+")";
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
        if(!run.isNull("display_pace"))addText(body,"Displayed pace · "+displayPace(run)+"\n"+adjustmentLabel()+" where available",14,muted,false,12);
        if(!run.isNull("average_hr"))addText(body,"Average heart rate · "+Math.round(run.optDouble("average_hr"))+" bpm",16,ink,false,20);
        if(!run.isNull("hr_under_percent"))addText(body,Math.round(run.optDouble("hr_under_percent"))+"% of time below your HR ceiling · "+(run.optString("hr_source").contains("average")?"estimated from average HR":"recorded samples"),14,muted,false,8);
        if(effort!=null)addText(body,"Fastest continuous 5K · "+raceTime(effort.optDouble("duration")),18,ink,true,20);
        if(point!=null)addText(body,pointDescription(point,null,null,"trial".equals(point.optString("category"))||"prediction".equals(point.optString("category"))||"easy_prediction".equals(point.optString("category"))),14,muted,false,16);
        LinearLayout more=section();addText(more,detail,14,muted,false,12);disclosure(body,"Recording & source details",more);
        final Dialog[] page={null};page[0]=fullScreen("Session",body,popup->{
            popup.getMenu().add("Change category").setEnabled(!busy).setOnMenuItemClickListener(item->{page[0].dismiss();chooseCategory(run);return true;});
            if(category.equals("short")||category.equals("medium")||category.equals("long"))popup.getMenu().add("Correct work laps").setEnabled(!busy).setOnMenuItemClickListener(item->{page[0].dismiss();chooseLaps(run);return true;});
        });
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
