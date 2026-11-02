package es.gmartos.tvhub.avisos;

import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.hardware.display.DisplayManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;
import android.util.DisplayMetrics;
import android.util.TypedValue;
import android.view.Display;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Una tarjeta encima de lo que se esté viendo, que no coge el mando (ni foco ni toques) y se va sola.
 * Un aviso nuevo sustituye al anterior.
 */
final class Aviso {
    private static final Handler PRINCIPAL = new Handler(Looper.getMainLooper());
    private static final Runnable QUITAR = new Runnable() {
        @Override
        public void run() {
            ocultar();
        }
    };
    private static WindowManager gestor;
    private static View actual;
    private static int turno;  // una imagen que llega tarde no se pega al aviso siguiente

    private Aviso() {
    }

    static final class Datos {
        final String titulo;
        final String detalle;
        final String mensaje;
        final String posicion;
        final String imagen;
        final int segundos;
        final int tamano;

        Datos(Intent o) {
            titulo = recorta(o.getStringExtra("titulo"), 90);
            detalle = recorta(o.getStringExtra("detalle"), 140);
            mensaje = recorta(o.getStringExtra("mensaje"), 700);
            posicion = recorta(o.getStringExtra("posicion"), 10);
            imagen = recorta(o.getStringExtra("imagen"), 600);
            segundos = limita(o.getIntExtra("segundos", 8), 2, 120);
            tamano = limita(o.getIntExtra("tamano", 40), 18, 96);
        }
    }

    static void mostrar(Context app, Datos d) {
        ocultar();
        Context ctx = contextoDeVentana(app);
        DisplayMetrics m = ctx.getResources().getDisplayMetrics();
        float dp = m.density;
        boolean conImagen = d.imagen.startsWith("http");
        int margen = (int) (26 * dp);
        int anchoTarjeta = (int) (m.widthPixels * 0.74f);
        int anchoCartel = (int) (150 * dp);
        int anchoTexto = anchoTarjeta - 4 * margen - (conImagen ? anchoCartel + margen : 0);

        LinearLayout tarjeta = new LinearLayout(ctx);
        tarjeta.setOrientation(LinearLayout.HORIZONTAL);
        tarjeta.setGravity(Gravity.CENTER_VERTICAL);
        tarjeta.setPadding(margen * 2, margen, margen * 2, margen);
        GradientDrawable fondo = new GradientDrawable();
        fondo.setColor(0xF20B1220);
        fondo.setCornerRadius(28 * dp);
        fondo.setStroke((int) Math.max(2, 3 * dp), 0xFF38BDF8);
        tarjeta.setBackground(fondo);

        // El hueco del cartel se reserva desde el principio (la imagen llega después): si no, al medir la tarjeta
        // no cuenta con él y la ventana sale estrecha y altísima
        ImageView cartel = new ImageView(ctx);
        cartel.setVisibility(conImagen ? View.VISIBLE : View.GONE);
        cartel.setScaleType(ImageView.ScaleType.CENTER_CROP);
        GradientDrawable hueco = new GradientDrawable();
        hueco.setColor(0xFF1E293B);
        hueco.setCornerRadius(14 * dp);
        cartel.setBackground(hueco);
        cartel.setClipToOutline(true);
        LinearLayout.LayoutParams pc = new LinearLayout.LayoutParams(anchoCartel, (int) (anchoCartel * 1.47f));
        pc.rightMargin = margen;
        tarjeta.addView(cartel, pc);

        LinearLayout textos = new LinearLayout(ctx);
        textos.setOrientation(LinearLayout.VERTICAL);
        textos.setGravity(conImagen ? Gravity.START : Gravity.CENTER_HORIZONTAL);
        tarjeta.addView(textos, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT));

        int alineado = conImagen ? Gravity.START : Gravity.CENTER_HORIZONTAL;
        if (!d.titulo.isEmpty()) {
            textos.addView(texto(ctx, d.titulo, d.tamano, 0xFFFFFFFF, true, anchoTexto, alineado));
        }
        if (!d.detalle.isEmpty()) {
            textos.addView(conMargen(texto(ctx, d.detalle, d.tamano * 0.6f, 0xFFFBBF24, true, anchoTexto, alineado),
                    (int) (8 * dp)));
        }
        if (!d.mensaje.isEmpty()) {
            float t = d.mensaje.length() > 200 ? d.tamano * 0.48f : d.tamano * 0.66f;
            TextView m2 = texto(ctx, d.mensaje, t, 0xFFE2E8F0, false, anchoTexto, alineado);
            m2.setMaxLines(9);
            m2.setEllipsize(TextUtils.TruncateAt.END);
            textos.addView(conMargen(m2, (int) (12 * dp)));
        }

        // Ancho medido aquí y fijado en la ventana: con WRAP_CONTENT Android prueba primero el ancho de un diálogo
        // (440 dp en esta TV) y, como el texto cabe partiéndolo en más líneas, la tarjeta sale estrecha y altísima
        tarjeta.measure(View.MeasureSpec.makeMeasureSpec(anchoTarjeta, View.MeasureSpec.AT_MOST),
                View.MeasureSpec.makeMeasureSpec(m.heightPixels, View.MeasureSpec.AT_MOST));
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                Math.min(Math.max(tarjeta.getMeasuredWidth(), 1), anchoTarjeta),
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        if ("arriba".equals(d.posicion)) {
            lp.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL;
            lp.y = (int) (40 * dp);
        } else if ("abajo".equals(d.posicion)) {
            lp.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
            lp.y = (int) (40 * dp);
        } else {
            lp.gravity = Gravity.CENTER;
        }
        lp.windowAnimations = android.R.style.Animation_Toast;
        lp.setTitle("TV Hub Avisos");

        gestor = (WindowManager) ctx.getSystemService(Context.WINDOW_SERVICE);
        gestor.addView(tarjeta, lp);
        actual = tarjeta;
        final int mio = ++turno;
        PRINCIPAL.removeCallbacks(QUITAR);
        PRINCIPAL.postDelayed(QUITAR, d.segundos * 1000L);
        if (conImagen) {
            descargar(d.imagen, cartel, mio);
        }
    }

    static void ocultar() {
        PRINCIPAL.removeCallbacks(QUITAR);
        if (actual != null && gestor != null) {
            try {
                gestor.removeViewImmediate(actual);
            } catch (RuntimeException ignorada) {
                // ya no estaba
            }
        }
        actual = null;
    }

    private static Context contextoDeVentana(Context app) {
        if (Build.VERSION.SDK_INT >= 30) {
            DisplayManager dm = (DisplayManager) app.getSystemService(Context.DISPLAY_SERVICE);
            Display pantalla = dm.getDisplay(Display.DEFAULT_DISPLAY);
            if (pantalla != null) {
                return app.createDisplayContext(pantalla)
                        .createWindowContext(WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY, null);
            }
        }
        return app;
    }

    private static void descargar(final String direccion, final ImageView cartel, final int mio) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                Bitmap leida = null;
                HttpURLConnection c = null;
                try {
                    c = (HttpURLConnection) new URL(direccion).openConnection();
                    c.setConnectTimeout(3000);
                    c.setReadTimeout(5000);
                    InputStream entrada = c.getInputStream();
                    try {
                        leida = BitmapFactory.decodeStream(entrada);
                    } finally {
                        entrada.close();
                    }
                } catch (Exception ignorada) {
                    // sin cartel: el aviso sale igual, solo con texto
                } finally {
                    if (c != null) {
                        c.disconnect();
                    }
                }
                final Bitmap imagen = leida;
                if (imagen == null) {
                    return;
                }
                PRINCIPAL.post(new Runnable() {
                    @Override
                    public void run() {
                        if (mio == turno && actual != null) {
                            cartel.setImageBitmap(imagen);
                            cartel.setVisibility(View.VISIBLE);
                        }
                    }
                });
            }
        }, "cartel").start();
    }

    private static TextView texto(Context ctx, String s, float sp, int color, boolean negrita, int ancho,
                                  int alineado) {
        TextView t = new TextView(ctx);
        t.setText(s);
        t.setTextColor(color);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTypeface(Typeface.create(Typeface.SANS_SERIF, negrita ? Typeface.BOLD : Typeface.NORMAL));
        t.setGravity(alineado);
        t.setMaxWidth(Math.max(ancho, 200));
        t.setLineSpacing(0, 1.12f);
        t.setShadowLayer(6, 0, 2, 0xCC000000);
        return t;
    }

    private static View conMargen(View v, int arriba) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.topMargin = arriba;
        v.setLayoutParams(lp);
        return v;
    }

    private static String recorta(String s, int maximo) {
        if (s == null) {
            return "";
        }
        s = s.trim();
        return s.length() > maximo ? s.substring(0, maximo - 1) + "…" : s;
    }

    private static int limita(int v, int minimo, int maximo) {
        return Math.max(minimo, Math.min(maximo, v));
    }
}
