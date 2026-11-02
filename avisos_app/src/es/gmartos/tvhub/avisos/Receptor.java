package es.gmartos.tvhub.avisos;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.provider.Settings;

/**
 * Recibe las órdenes del hub por ADB:
 *   am broadcast -f 32 -n es.gmartos.tvhub.avisos/.Receptor -a es.gmartos.tvhub.AVISO
 *      --es titulo T --es detalle D --es mensaje M --es imagen URL --ei segundos 8 --ei tamano 40 --es posicion centro
 * Contesta con el código del resultado: 1 enseñado, 2 sin permiso para pintar encima, 3 fallo, 4 orden desconocida.
 */
public class Receptor extends BroadcastReceiver {
    static final String AVISO = "es.gmartos.tvhub.AVISO";
    static final String OCULTAR = "es.gmartos.tvhub.OCULTAR";

    @Override
    public void onReceive(Context contexto, Intent orden) {
        Context app = contexto.getApplicationContext();
        String accion = orden.getAction();
        if (OCULTAR.equals(accion)) {
            Aviso.ocultar();
            responder(1, "oculto");
            return;
        }
        if (!AVISO.equals(accion)) {
            responder(4, "orden desconocida");
            return;
        }
        if (!Settings.canDrawOverlays(app)) {
            responder(2, "sin permiso para pintar encima");
            return;
        }
        try {
            Aviso.mostrar(app, new Aviso.Datos(orden));
            responder(1, "ok");
        } catch (RuntimeException e) {
            responder(3, String.valueOf(e));
        }
    }

    private void responder(int codigo, String texto) {
        if (isOrderedBroadcast()) {
            setResultCode(codigo);
            setResultData(texto);
        }
    }
}
