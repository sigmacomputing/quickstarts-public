import { Injectable } from '@angular/core';
import { client } from '@sigmacomputing/plugin';

@Injectable({
    providedIn: 'root'
})
export class ActionTriggerService {

    /**
     * triggers an action for the registered action trigger
     * @param configId ID from the config of type: 'action-trigger'
     */
    triggerAction(configId: string): void {
        client.config.triggerAction(configId);
    }

    /**
     * returns a callback function to trigger the action
     * @param configId ID from the config of type: 'action-trigger'
     * @returns A callback function to trigger the action
     */
    getActionTriggerCallback(configId: string): () => void {
        return () => {
            this.triggerAction(configId);
        };
    }
} 