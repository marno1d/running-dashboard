package dev.rundashboard.app;

import android.content.Context;
import com.chaquo.python.Python;
import com.chaquo.python.PyObject;
import com.chaquo.python.android.AndroidPlatform;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONObject;

/** All Python and SQLite access stays on one process-wide worker, including services. */
final class BackendRuntime {
    static final ExecutorService WORKER = Executors.newSingleThreadExecutor();
    private static PyObject backend;
    private static boolean ready;

    static JSONObject initialize(Context context) throws Exception {
        Context app=context.getApplicationContext();
        if(ready)return invoke(app,"status");
        System.loadLibrary("android-support");
        System.loadLibrary("ffi");
        System.loadLibrary("c++_shared-d523468d");
        if(!Python.isStarted())Python.start(new AndroidPlatform(app));
        backend=Python.getInstance().getModule("garmin_backend");
        invoke(app,"configure_cache",new java.io.File(app.getFilesDir(),"run-cache.sqlite").getAbsolutePath());
        SessionStore store=new SessionStore(app);
        JSONObject saved;
        try{saved=store.load();}catch(Exception error){store.clear();saved=null;}
        JSONObject state=invoke(app,"restore",saved==null?"":saved.toString());
        ready=true;
        return state;
    }

    static JSONObject invoke(Context context,String operation,Object... args) throws Exception {
        Object[] callArgs=new Object[args.length+1];
        callArgs[0]=operation;System.arraycopy(args,0,callArgs,1,args.length);
        JSONObject result=new JSONObject(backend.callAttr("call",callArgs).toString());
        if(result.optBoolean("ok")&&result.optBoolean("authenticated")&&!result.isNull("tokens"))
            new SessionStore(context.getApplicationContext()).save(result.getJSONObject("tokens"));
        return result;
    }
}
