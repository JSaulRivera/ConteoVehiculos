/* =========================================================
   CONFIGURACIÓN
========================================================= */

const INTERVALO_ESTADO = 1000;
const INTERVALO_EVENTOS = 3000;


/* =========================================================
   ELEMENTOS
========================================================= */

const disponiblesElement =
    document.getElementById("disponibles");

const ocupadosElement =
    document.getElementById("ocupados");

const totalElement =
    document.getElementById("total");

const deteccionesElement =
    document.getElementById("detecciones");

const sidebarDisponibles =
    document.getElementById("sidebarDisponibles");

const sidebarOcupados =
    document.getElementById("sidebarOcupados");

const sidebarTotal =
    document.getElementById("sidebarTotal");

const fpsElement =
    document.getElementById("fps");

const cameraStatus =
    document.getElementById("cameraStatus");

const cameraIndicator =
    document.getElementById("cameraIndicator");

const lastUpdate =
    document.getElementById("lastUpdate");

const zonasLista =
    document.getElementById("zonasLista");

const zonasDashboard =
    document.getElementById("zonasDashboard");

const deteccionesLista =
    document.getElementById("deteccionesLista");

const eventosTabla =
    document.getElementById("eventosTabla");

const refreshEvents =
    document.getElementById("refreshEvents");

const modeloViewer = document.getElementById('modeloGLB');
        modeloViewer.src = MODELO_GLB_URL;
/* =========================================================
   OBTENER ESTADO
========================================================= */

async function obtenerEstado() {

    try {
        
        const response =
            await fetch(API_ESTADO_URL, {
                cache: "no-store"
            });


        if (!response.ok) {

            throw new Error(
                "Error HTTP " +
                response.status
            );
        }


        const data =
            await response.json();


        actualizarEstadisticas(data);

        actualizarCamara(data);

        actualizarZonas(data.zonas);

        actualizarDetecciones(
            data.objetos
        );


    } catch (error) {

        console.error(
            "Error obteniendo estado:",
            error
        );

        cameraStatus.textContent =
            "Sin conexión";

        cameraIndicator.classList
            .remove("connected");
    }
}


/* =========================================================
   ESTADÍSTICAS
========================================================= */

function actualizarEstadisticas(data) {

    disponiblesElement.textContent =
        data.disponibles;

    ocupadosElement.textContent =
        data.ocupados;

    totalElement.textContent =
        data.total;

    deteccionesElement.textContent =
        data.detecciones;


    sidebarDisponibles.textContent =
        data.disponibles;

    sidebarOcupados.textContent =
        data.ocupados;

    sidebarTotal.textContent =
        data.total;


    fpsElement.textContent =
        `FPS: ${data.fps}`;


    lastUpdate.textContent =
        data.ultima_actualizacion;
}


/* =========================================================
   ESTADO CÁMARA
========================================================= */

function actualizarCamara(data) {

    cameraStatus.textContent =
        data.camara;


    if (
        data.camara === "Conectada"
    ) {

        cameraIndicator.classList
            .add("connected");

    } else {

        cameraIndicator.classList
            .remove("connected");
    }
}


/* =========================================================
   ZONAS
========================================================= */

function actualizarZonas(zonas) {

    zonasLista.innerHTML = "";

    zonasDashboard.innerHTML = "";


    Object.entries(zonas).forEach(
        ([numero, zona]) => {

            crearZonaSidebar(
                numero,
                zona
            );

            crearZonaDashboard(
                numero,
                zona
            );

        }
    );
}


/* =========================================================
   ZONA SIDEBAR
========================================================= */

function crearZonaSidebar(
    numero,
    zona
) {

    const elemento =
        document.createElement("div");


    elemento.className =
        "zona-side";


    const estadoClase =
        zona.ocupada
            ? "ocupada"
            : "";


    const estadoTexto =
        zona.ocupada
            ? "OCUPADA"
            : "LIBRE";


    elemento.innerHTML = `

        <div class="zona-side-left">

            <span
                class="zona-dot ${estadoClase}"
            ></span>

            <span>
                Zona ${numero}
            </span>

        </div>

        <span
            class="zona-side-status ${estadoClase}"
        >
            ${estadoTexto}
        </span>

    `;


    zonasLista.appendChild(
        elemento
    );
}


/* =========================================================
   ZONA DASHBOARD
========================================================= */

function crearZonaDashboard(
    numero,
    zona
) {

    const elemento =
        document.createElement("div");


    elemento.className =
        "zona-card";


    if (zona.ocupada) {

        elemento.classList.add(
            "ocupada"
        );
    }


    const estado =
        zona.ocupada
            ? "OCUPADO"
            : "LIBRE";


    const trackId =
        zona.track_id !== null
            ? `ID: ${zona.track_id}`
            : "Sin vehículo";


    elemento.innerHTML = `

        <h3>
            ZONA ${numero}
        </h3>

        <div class="estado">
            ${estado}
        </div>

        <div class="zona-id">
            ${trackId}
        </div>

        <div class="cronometro">
            ${zona.tiempo}
        </div>

    `;


    zonasDashboard.appendChild(
        elemento
    );
}


/* =========================================================
   DETECCIONES
========================================================= */

function actualizarDetecciones(
    objetos
) {

    deteccionesLista.innerHTML = "";


    if (
        !objetos ||
        objetos.length === 0
    ) {

        deteccionesLista.innerHTML = `

            <div class="empty-state">

                <span>
                    🔍
                </span>

                No hay objetos detectados

            </div>

        `;

        return;
    }


    objetos.forEach(
        objeto => {

            const elemento =
                document.createElement(
                    "div"
                );


            elemento.className =
                "detection-item";


            const idTexto =
                objeto.id !== null
                    ? `ID ${objeto.id}`
                    : "Sin ID";


            let icono = "🚗";


            if (
                objeto.nombre ===
                "person"
            ) {

                icono = "👤";

            } else if (
                objeto.nombre ===
                "truck"
            ) {

                icono = "🚚";
            }


            elemento.innerHTML = `

                <div class="detection-info">

                    <div
                        class="detection-icon"
                    >
                        ${icono}
                    </div>

                    <div>

                        <div
                            class="detection-name"
                        >
                            ${objeto.nombre}
                        </div>

                        <span
                            class="detection-id"
                        >
                            ${idTexto}
                        </span>

                    </div>

                </div>


                <div
                    class="confidence"
                >
                    ${objeto.confianza}%
                </div>

            `;


            deteccionesLista.appendChild(
                elemento
            );

        }
    );
}


/* =========================================================
   EVENTOS
========================================================= */

async function obtenerEventos() {

    try {

        const response =
            await fetch(
                API_EVENTOS_URL,
                {
                    cache: "no-store"
                }
            );


        if (!response.ok) {

            throw new Error(
                "Error HTTP " +
                response.status
            );
        }


        const eventos =
            await response.json();


        mostrarEventos(eventos);


    } catch (error) {

        console.error(
            "Error obteniendo eventos:",
            error
        );

    }
}


/* =========================================================
   MOSTRAR EVENTOS
========================================================= */

function mostrarEventos(
    eventos
) {

    eventosTabla.innerHTML = "";


    if (
        !eventos ||
        eventos.length === 0
    ) {

        eventosTabla.innerHTML = `

            <tr>

                <td
                    colspan="6"
                    class="empty-table"
                >
                    No hay eventos registrados
                </td>

            </tr>

        `;

        return;
    }


    eventos.forEach(
        evento => {

            const fila =
                document.createElement(
                    "tr"
                );


            const claseEvento =
                evento.Evento ===
                "ENTRADA"
                    ? "evento-entrada"
                    : "evento-salida";


            const duracion =
                evento.Duración
                    ? evento.Duración
                    : "--";


            let imagenHTML =
                "--";


            if (
                evento.Imagen
            ) {

                const carpeta =
                    evento.Evento ===
                    "ENTRADA"
                        ? "capturas_entrada"
                        : "capturas_salida";


                imagenHTML = `

                    <a
                        class="image-link"
                        href="/${carpeta}/${encodeURIComponent(evento.Imagen)}"
                        target="_blank"
                    >
                        Ver imagen
                    </a>

                `;
            }


            fila.innerHTML = `

                <td
                    class="${claseEvento}"
                >
                    ${evento.Evento || "--"}
                </td>

                <td>
                    ${evento.ID || "--"}
                </td>

                <td>
                    Zona ${evento.Zona || "--"}
                </td>

                <td>
                    ${evento.Hora || "--"}
                </td>

                <td>
                    ${duracion}
                </td>

                <td>
                    ${imagenHTML}
                </td>

            `;


            eventosTabla.appendChild(
                fila
            );

        }
    );
}


/* =========================================================
   BOTÓN ACTUALIZAR
========================================================= */

refreshEvents.addEventListener(
    "click",
    obtenerEventos
);


/* =========================================================
   INICIAR
========================================================= */

obtenerEstado();

obtenerEventos();


setInterval(
    obtenerEstado,
    INTERVALO_ESTADO
);


setInterval(
    obtenerEventos,
    INTERVALO_EVENTOS
);