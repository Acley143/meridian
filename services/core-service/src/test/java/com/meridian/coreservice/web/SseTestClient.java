package com.meridian.coreservice.web;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * Minimal real-HTTP SSE test client: a genuine {@code java.net.http.HttpClient} streaming
 * connection (not RestAssured, which isn't built for a body that never closes), reading {@code
 * id:}/{@code event:}/{@code data:} lines as they arrive and handing parsed events to the caller
 * via a queue. Used only by SSE resume tests.
 */
final class SseTestClient implements AutoCloseable {

  record SseEvent(String id, String eventName, String data) {}

  private final HttpClient httpClient = HttpClient.newHttpClient();
  private final BlockingQueue<SseEvent> events = new LinkedBlockingQueue<>();
  private final Thread readerThread;
  private volatile boolean closed = false;
  private volatile int statusCode = -1;

  SseTestClient(String url, String lastEventId) {
    HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create(url)).GET();
    if (lastEventId != null) {
      builder.header("Last-Event-ID", lastEventId);
    }
    HttpRequest request = builder.build();

    readerThread =
        new Thread(
            () -> {
              try {
                HttpResponse<java.io.InputStream> response =
                    httpClient.send(request, HttpResponse.BodyHandlers.ofInputStream());
                statusCode = response.statusCode();
                if (statusCode != 200) {
                  return;
                }
                try (BufferedReader reader =
                    new BufferedReader(
                        new InputStreamReader(response.body(), StandardCharsets.UTF_8))) {
                  String id = null;
                  String eventName = null;
                  StringBuilder data = new StringBuilder();
                  String line;
                  while (!closed && (line = reader.readLine()) != null) {
                    if (line.isEmpty()) {
                      if (id != null || data.length() > 0 || eventName != null) {
                        events.put(new SseEvent(id, eventName, data.toString()));
                      }
                      id = null;
                      eventName = null;
                      data = new StringBuilder();
                    } else if (line.startsWith("id:")) {
                      id = line.substring(3).trim();
                    } else if (line.startsWith("event:")) {
                      eventName = line.substring(6).trim();
                    } else if (line.startsWith("data:")) {
                      data.append(line.substring(5).trim());
                    }
                  }
                }
              } catch (IOException | InterruptedException e) {
                // Expected on close()/disconnect -- the stream never ends on its own.
              }
            },
            "sse-test-client-reader");
    readerThread.setDaemon(true);
    readerThread.start();
  }

  int statusCode(Duration timeout) throws InterruptedException {
    long deadline = System.currentTimeMillis() + timeout.toMillis();
    while (statusCode == -1 && System.currentTimeMillis() < deadline) {
      Thread.sleep(20);
    }
    return statusCode;
  }

  SseEvent nextEvent(Duration timeout) throws InterruptedException {
    return events.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
  }

  List<SseEvent> drainAvailable(int expectedCount, Duration timeout) throws InterruptedException {
    List<SseEvent> result = new ArrayList<>();
    long deadline = System.currentTimeMillis() + timeout.toMillis();
    while (result.size() < expectedCount && System.currentTimeMillis() < deadline) {
      SseEvent event = events.poll(200, TimeUnit.MILLISECONDS);
      if (event != null) {
        result.add(event);
      }
    }
    return result;
  }

  @Override
  public void close() {
    closed = true;
    readerThread.interrupt();
  }
}
