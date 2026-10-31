/*
 * Estensione del web process di WebKitGTK 4.1.
 * Su ogni richiesta HTTP aggiunge "Sec-GPC: 1" e riduce il Referer
 * alla sola origine (schema://host[:porta]/).
 *
 * Con gli header di sviluppo (libwebkit2gtk-4.1-dev) build.sh definisce
 * SR_WEBKIT_HEADERS e il compilatore controlla le firme. Senza, dichiariamo
 * qui le poche funzioni dell'API pubblica che usiamo: i simboli li fornisce
 * il web process che carica questa libreria.
 */
#include <string.h>
#include <glib-object.h>
#include <gmodule.h>

#ifdef SR_WEBKIT_HEADERS
#include <webkit2/webkit-web-extension.h>
#else
typedef struct _WebKitWebExtension WebKitWebExtension;
typedef struct _WebKitWebPage WebKitWebPage;
typedef struct _WebKitURIRequest WebKitURIRequest;
typedef struct _WebKitURIResponse WebKitURIResponse;
typedef struct _SoupMessageHeaders SoupMessageHeaders;

SoupMessageHeaders *webkit_uri_request_get_http_headers(WebKitURIRequest *request);
const char *soup_message_headers_get_one(SoupMessageHeaders *hdrs, const char *name);
void soup_message_headers_replace(SoupMessageHeaders *hdrs, const char *name, const char *value);
void soup_message_headers_remove(SoupMessageHeaders *hdrs, const char *name);
#endif

static gboolean send_gpc = TRUE;
static gboolean trim_referer = TRUE;

/* "https://a.b:8080/x?y" -> "https://a.b:8080/"; NULL se non è un URL valido */
static char *origin_of(const char *url)
{
    const char *sep = strstr(url, "://");
    if (sep == NULL || sep == url)
        return NULL;
    const char *host = sep + 3;
    size_t host_len = strcspn(host, "/?#");
    if (host_len == 0)
        return NULL;
    return g_strdup_printf("%.*s/", (int)(host - url + host_len), url);
}

static gboolean on_send_request(WebKitWebPage *page, WebKitURIRequest *request,
                                WebKitURIResponse *redirected_response, gpointer data)
{
    (void)page;
    (void)redirected_response;
    (void)data;

    /* NULL per richieste non HTTP (data:, devtox:, ...) */
    SoupMessageHeaders *headers = webkit_uri_request_get_http_headers(request);
    if (headers == NULL)
        return FALSE;

    if (send_gpc)
        soup_message_headers_replace(headers, "Sec-GPC", "1");

    if (trim_referer) {
        const char *referer = soup_message_headers_get_one(headers, "Referer");
        if (referer != NULL) {
            char *origin = origin_of(referer);
            if (origin != NULL)
                soup_message_headers_replace(headers, "Referer", origin);
            else
                soup_message_headers_remove(headers, "Referer");
            g_free(origin);
        }
    }
    return FALSE; /* FALSE = la richiesta prosegue */
}

static void on_page_created(WebKitWebExtension *extension, WebKitWebPage *page, gpointer data)
{
    (void)extension;
    (void)data;
    g_signal_connect(page, "send-request", G_CALLBACK(on_send_request), NULL);
}

/* Punto d'ingresso chiamato da WebKit; user_data arriva dal browser: (bb) */
G_MODULE_EXPORT void webkit_web_extension_initialize_with_user_data(WebKitWebExtension *extension,
                                                                     GVariant *user_data)
{
    if (user_data != NULL && g_variant_is_of_type(user_data, G_VARIANT_TYPE("(bb)")))
        g_variant_get(user_data, "(bb)", &send_gpc, &trim_referer);
    g_signal_connect(extension, "page-created", G_CALLBACK(on_page_created), NULL);
}
