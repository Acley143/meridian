package com.meridian.coreservice.web;

import com.meridian.coreservice.kafka.RiskSnapshotPersistedEvent;
import com.meridian.coreservice.persistence.domain.RiskSnapshotRecord;
import com.meridian.coreservice.web.dto.RiskSnapshotDto;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * In-process fan-out from "a risk snapshot was durably written" (05c's {@code
 * RiskSnapshotRepositoryWriter}) to every live SSE subscriber for that portfolio. Publishing
 * happens AFTER the database write succeeds, never before -- a snapshot the dashboard sees live
 * must already be replayable on the next reconnect (ADR-0012's whole premise).
 */
@Component
public class RiskSnapshotBroadcaster {

  private final Map<String, List<SseEmitter>> subscribersByPortfolio = new ConcurrentHashMap<>();

  public void subscribe(String portfolioId, SseEmitter emitter) {
    List<SseEmitter> subscribers =
        subscribersByPortfolio.computeIfAbsent(portfolioId, id -> new CopyOnWriteArrayList<>());
    subscribers.add(emitter);
    Runnable unsubscribe = () -> subscribers.remove(emitter);
    emitter.onCompletion(unsubscribe);
    emitter.onTimeout(unsubscribe);
    emitter.onError(e -> unsubscribe.run());
  }

  @EventListener
  public void onSnapshotPersisted(RiskSnapshotPersistedEvent event) {
    publish(event.snapshot());
  }

  public void publish(RiskSnapshotRecord snapshot) {
    List<SseEmitter> subscribers = subscribersByPortfolio.get(snapshot.portfolioId());
    if (subscribers == null || subscribers.isEmpty()) {
      return;
    }
    String eventId =
        new SseEventId(snapshot.portfolioId(), snapshot.asOf(), snapshot.pricerVersion()).format();
    RiskSnapshotDto dto = RiskSnapshotDtoMapper.toDto(snapshot);
    for (SseEmitter emitter : subscribers) {
      try {
        emitter.send(SseEmitter.event().id(eventId).data(dto));
      } catch (IOException e) {
        subscribers.remove(emitter);
      }
    }
  }
}
