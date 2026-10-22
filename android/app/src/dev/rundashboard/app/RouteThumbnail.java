package dev.rundashboard.app;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.TextView;
import org.json.JSONObject;

/** Small relative GPS shape; missing and failed recordings have explicit states. */
final class RouteThumbnail extends FrameLayout {
    private final RouteView route;
    private final TextView status;
    RouteThumbnail(Context context,MaterialPalette palette){
        super(context);
        route=new RouteView(context,palette,true);
        route.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        addView(route,new FrameLayout.LayoutParams(-1,-1));
        status=new TextView(context);status.setTextSize(11);status.setTextColor(palette.muted);status.setGravity(Gravity.CENTER);
        status.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        addView(status,new FrameLayout.LayoutParams(-1,-1));
        setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
    }
    private void label(String text){
        route.setVisibility(View.GONE);status.setVisibility(View.VISIBLE);status.setText(text);
        setOnClickListener(null);setClickable(false);setFocusable(false);setContentDescription(null);
        setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
    }
    void showWaiting(){label("GPS");}
    void showLoading(){label("Loading\nGPS…");}
    void showRoute(JSONObject outline){
        label("No GPS");if(route.setRoute(outline)){status.setVisibility(View.GONE);route.setVisibility(View.VISIBLE);}
    }
    void showRetry(Runnable retry){
        label("Retry\nGPS");setOnClickListener(v->retry.run());setFocusable(true);
        setContentDescription("GPS preview unavailable. Retry loading GPS.");setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);
    }
}
