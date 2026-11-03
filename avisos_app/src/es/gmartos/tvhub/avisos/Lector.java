package es.gmartos.tvhub.avisos;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.Instrumentation;
import android.app.UiAutomation;
import android.graphics.Rect;
import android.os.Bundle;
import android.view.accessibility.AccessibilityNodeInfo;

/**
 * Lee los textos de la pantalla que se ve (por ejemplo, el programa marcado en la guía de la tele).
 * Solo lo puede lanzar el ADB, y solo cuando el hub lo pide:
 *   am instrument -w es.gmartos.tvhub.avisos/.Lector
 * No cambia ningún ajuste ni se queda funcionando: lee una vez y termina.
 * Devuelve «textos»: una línea por texto, «id<TAB>texto<TAB>marcas<TAB>x,y,ancho,alto»
 * (marcas: F = con el foco, S = seleccionado).
 * Mira la pantalla aunque no esté quieta: «uiautomator dump» se rinde con la guía porque su reloj no para.
 */
public class Lector extends Instrumentation {
    private static final int MAX_NODOS = 3000;
    private int nodos;

    @Override
    public void onCreate(Bundle argumentos) {
        super.onCreate(argumentos);
        start();
    }

    @Override
    public void onStart() {
        Bundle resultado = new Bundle();
        StringBuilder textos = new StringBuilder();
        try {
            UiAutomation ui = getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
            AccessibilityServiceInfo info = ui.getServiceInfo();
            if (info != null) {
                info.flags |= AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
                        | AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS;
                ui.setServiceInfo(info);
            }
            AccessibilityNodeInfo raiz = null;
            for (int i = 0; i < 30 && raiz == null; i++) {
                raiz = ui.getRootInActiveWindow();
                if (raiz == null) {
                    Thread.sleep(100);
                }
            }
            if (raiz == null) {
                resultado.putString("error", "sin ventana");
            } else {
                resultado.putString("paquete", String.valueOf(raiz.getPackageName()));
                recorrer(raiz, textos);
            }
        } catch (Throwable fallo) {
            resultado.putString("error", String.valueOf(fallo));
        }
        resultado.putString("textos", textos.toString());
        finish(0, resultado);
    }

    private void recorrer(AccessibilityNodeInfo nodo, StringBuilder textos) {
        if (nodo == null || nodos++ > MAX_NODOS) {
            return;
        }
        CharSequence texto = nodo.getText();
        if (texto == null || texto.length() == 0) {
            texto = nodo.getContentDescription();
        }
        if (texto != null && texto.length() > 0) {
            Rect caja = new Rect();
            nodo.getBoundsInScreen(caja);
            String id = nodo.getViewIdResourceName();
            textos.append(id == null ? "" : id.substring(id.indexOf('/') + 1)).append('\t')
                    .append(limpiar(texto)).append('\t')
                    .append(nodo.isFocused() ? "F" : "").append(nodo.isSelected() ? "S" : "").append('\t')
                    .append(caja.left).append(',').append(caja.top).append(',')
                    .append(caja.width()).append(',').append(caja.height()).append('\n');
        }
        for (int i = 0; i < nodo.getChildCount(); i++) {
            recorrer(nodo.getChild(i), textos);
        }
    }

    private static String limpiar(CharSequence texto) {
        return texto.toString().replace('\t', ' ').replace('\r', ' ').replace('\n', ' ').trim();
    }
}
