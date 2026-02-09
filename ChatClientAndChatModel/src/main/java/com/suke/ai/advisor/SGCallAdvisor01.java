package com.suke.ai.advisor;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClientRequest;
import org.springframework.ai.chat.client.ChatClientResponse;
import org.springframework.ai.chat.client.advisor.api.CallAdvisor;
import org.springframework.ai.chat.client.advisor.api.CallAdvisorChain;

/**
 * @author 自然醒
 * @version 1.0
 */
@Slf4j
public class SGCallAdvisor01 implements CallAdvisor {
    @Override
    public ChatClientResponse adviseCall(ChatClientRequest chatClientRequest, CallAdvisorChain callAdvisorChain) {
        log.info("advisor增强响应开始 -> {}", chatClientRequest);
        ChatClientResponse chatClientResponse = callAdvisorChain.nextCall(chatClientRequest);
        log.info("advisor增强响应结束 -> {}", chatClientResponse);
        return chatClientResponse;
    }

    @Override
    public String getName() {
        return "SGCallAdvisor01";
    }

    @Override
    public int getOrder() {
        return 0;
    }
}
