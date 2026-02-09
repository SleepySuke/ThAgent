package com.suke.ai.config;

import com.alibaba.cloud.ai.dashscope.api.DashScopeApi;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * @author 自然醒
 * @version 1.0
 */
@Configuration
@Slf4j
public class SaaLLMConfig {

    @Value("${spring.ai.dashscope.api-key}")
    private String apiKey;
    /**
     * 配置LLM
     * 使用yml文件读取配置
     */
    @Bean
    @ConditionalOnMissingBean
    public DashScopeApi dashScopeApi(){
        System.out.println("apiKey:"+apiKey);
        return DashScopeApi.builder()
                .apiKey(apiKey)
                .build();
    }

    @Bean
    @ConditionalOnMissingBean
    public ChatClient chatClient(ChatModel chatModel){
        return ChatClient.builder(chatModel).build();
    }

    /**
     * 配置LLM
     * 可以通过环境变量读取apiKey
     * System.getenv("DASH_SCOPE_API_KEY")
     */
//    @Bean
//    public DashScopeApi dashScopeApi2(){
//        return DashScopeApi.builder()
//                .apiKey(System.getenv("DASH_SCOPE_API_KEY"))
//                .build();
//    }
}
